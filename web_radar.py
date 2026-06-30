# -*- coding: utf-8 -*-
"""
통합 입찰공고 레이더 (Streamlit)
- 나라장터 / 국방부 / LH / 가스공사 / 수자원공사 5개 기관 통합 조회
- GitHub 레포(예: won2222)에 app.py + requirements.txt로 올려서
  Streamlit Community Cloud(share.streamlit.io)에 배포하는 구조

실행(로컬 테스트):
    pip install -r requirements.txt
    streamlit run app.py
"""

import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import unquote
import re
import io

# =====================================================================
# 0. 공통 설정
# =====================================================================
st.set_page_config(page_title="입찰공고 통합 레이더", layout="wide")

SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

DEFAULT_KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성"]
REGION_FREE = ['전국', '제한없음']


def _region_token_pass(token: str) -> bool:
    token = token.strip()
    if not token:
        return True
    if any(f in token for f in REGION_FREE):
        return True
    if '평택' in token or '화성' in token:
        return True
    if token == '경기도':
        return True
    return False


def region_pass(region_text) -> bool:
    if region_text is None:
        return True
    if isinstance(region_text, (list, tuple, set)):
        tokens = list(region_text)
    else:
        text = str(region_text).strip()
        if text == '':
            return True
        tokens = re.split(r'[,]', text)
    if not tokens:
        return True
    return any(_region_token_pass(t) for t in tokens)


def to_row(source, notice_no, title, agency, close_dt, open_dt, amount, region, keyword, extra=''):
    return {
        '출처기관': source, '공고번호': notice_no, '공고명': title, '수요/발주기관': agency,
        '마감일시': close_dt, '개찰일시': open_dt, '금액(원)': amount,
        '지역제한': region, '매칭키워드': keyword, '비고': extra,
    }


def format_d2b_dt(val):
    """D2B의 'YYYYMMDDHHMM' 미가공 날짜를 'YYYY-MM-DD HH:MM'으로 변환"""
    if not val or str(val).strip() in ('', '-'):
        return '-'
    s = str(val).replace('.0', '').strip()
    try:
        if len(s) >= 12:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
        elif len(s) >= 8:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return s
    except Exception:
        return s


# =====================================================================
# 1. 기관별 수집 함수 (캐시: 같은 조건이면 10분간 재호출 안 함)
# =====================================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_narajangter(keywords, start, end):
    results = []
    service_key = unquote(SERVICE_KEY)
    s_date = start.strftime("%Y%m%d0000")
    e_date = end.strftime("%Y%m%d2359")
    url_base = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'

    all_raw = []
    for kw in keywords:
        params = {'serviceKey': service_key, 'numOfRows': '100', 'type': 'json',
                  'inqryDiv': '1', 'inqryBgnDt': s_date, 'inqryEndDt': e_date, 'bidNtceNm': kw}
        try:
            res = requests.get(url_base + 'getBidPblancListInfoServcPPSSrch', params=params, timeout=10)
            items = res.json().get('response', {}).get('body', {}).get('items', [])
            if items:
                for it in ([items] if isinstance(items, dict) else items):
                    it['_keyword'] = kw
                    all_raw.append(it)
        except Exception:
            pass

    if not all_raw:
        return results

    df_bids = pd.DataFrame(all_raw).drop_duplicates(subset=['bidNtceNo'])
    for _, row in df_bids.iterrows():
        b_no, b_ord = row['bidNtceNo'], str(row.get('bidNtceOrd', '000')).zfill(3)
        region_val = ""
        try:
            r_res = requests.get(url_base + 'getBidPblancListInfoPrtcptPsblRgn',
                                  params={'ServiceKey': service_key, 'type': 'json', 'inqryDiv': '2',
                                          'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=8).json()
            r_items = r_res.get('response', {}).get('body', {}).get('items', [])
            regs = [str(ri.get('prtcptPsblRgnNm', '')) for ri in ([r_items] if isinstance(r_items, dict) else r_items)
                    if ri.get('prtcptPsblRgnNm')]
            region_val = ", ".join(set(regs)) if regs else "제한없음"
        except Exception:
            region_val = "확인불가"

        if not region_pass(region_val):
            continue

        results.append(to_row(
            source='나라장터', notice_no=b_no, title=row.get('bidNtceNm', '-'),
            agency=row.get('dminsttNm', '-'), close_dt=row.get('bidClseDt', '-'),
            open_dt=row.get('opengDt', '-'), amount=row.get('asignBdgtAmt', row.get('bdgtAmt', '-')),
            region=region_val, keyword=row.get('_keyword', '-')
        ))
    return results


@st.cache_data(ttl=600, show_spinner=False)
def fetch_d2b(keywords, start, end):
    results = []
    start_day, end_day = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    url_bid = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
    for kw in keywords:
        try:
            params = {'serviceKey': SERVICE_KEY, 'numOfRows': '200', '_type': 'json',
                      'anmtDateBegin': start_day, 'anmtDateEnd': end_day, 'bidNm': kw}
            res_b = requests.get(url_bid, params=params, headers=HEADERS, timeout=15)
            items = res_b.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])
            items = [items] if isinstance(items, dict) else (items or [])
            for it in items:
                bid_nm = it.get('bidNm', '')
                url_det = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancDetail"
                p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'),
                         'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'),
                         'dcsNo': it.get('dcsNo'), '_type': 'json'}
                area, open_dt, budget, g2b_no = "제한없음", it.get('opengDt', '-'), it.get('budgetAmount', 0), None
                try:
                    det = requests.get(url_det, params=p_det, headers=HEADERS, timeout=8).json() \
                        .get('response', {}).get('body', {}).get('item', {})
                    area = det.get('areaLmttList') or "제한없음"
                    open_dt = det.get('opengDt') or open_dt
                    budget = det.get('budgetAmount') or budget
                    g2b_no = det.get('g2bPblancNo')
                except Exception:
                    pass
                if not region_pass(area):
                    continue
                results.append(to_row(
                    source='국방부(일반경쟁)', notice_no=g2b_no or it.get('pblancNo', '-'), title=bid_nm,
                    agency=it.get('ornt', '-'), close_dt=format_d2b_dt(it.get('biddocPresentnClosDt', '-')),
                    open_dt=format_d2b_dt(open_dt), amount=budget, region=area, keyword=kw
                ))
        except Exception:
            pass

    url_priv = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList"
    for kw in keywords:
        try:
            p_priv = {'serviceKey': SERVICE_KEY, 'numOfRows': '200', '_type': 'json',
                      'prqudoPresentnClosDateBegin': start_day, 'prqudoPresentnClosDateEnd': end_day,
                      'othbcNtatNm': kw}
            res_p = requests.get(url_priv, params=p_priv, headers=HEADERS, timeout=15)
            items = res_p.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])
            items = [items] if isinstance(items, dict) else (items or [])
            for it in items:
                bid_nm = it.get('othbcNtatNm', '')
                url_det = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanDetail"
                p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'),
                         'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'),
                         'iemNo': it.get('iemNo'), 'ntatPlanDate': it.get('ntatPlanDate'), '_type': 'json'}
                area, open_dt, budget, g2b_no = "제한없음", it.get('opengDt', '-'), it.get('budgetAmount', 0), None
                try:
                    det = requests.get(url_det, params=p_det, headers=HEADERS, timeout=8).json() \
                        .get('response', {}).get('body', {}).get('item', {})
                    area = det.get('areaLmttList') or "제한없음"
                    open_dt = det.get('opengDt') or open_dt
                    budget = det.get('budgetAmount') or budget
                    g2b_no = det.get('g2bPblancNo')
                except Exception:
                    pass
                if not region_pass(area):
                    continue
                results.append(to_row(
                    source='국방부(공개수의)', notice_no=g2b_no or it.get('pblancNo', '-'), title=bid_nm,
                    agency=it.get('ornt', '-'), close_dt=format_d2b_dt(it.get('prqudoPresentnClosDt', '-')),
                    open_dt=format_d2b_dt(open_dt), amount=budget, region=area, keyword=kw,
                    extra='마감일자 기준 검색(공고일자 파라미터 없음)'
                ))
        except Exception:
            pass

    seen, dedup = set(), []
    for r in results:
        key = (r['출처기관'], r['공고번호'])
        if key not in seen:
            seen.add(key)
            dedup.append(r)
        else:
            for d in dedup:
                if (d['출처기관'], d['공고번호']) == key and r['매칭키워드'] not in d['매칭키워드']:
                    d['매칭키워드'] += f",{r['매칭키워드']}"
    return dedup


def lh_clean(text):
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip() if text else ""


@st.cache_data(ttl=600, show_spinner=False)
def fetch_lh(keywords, start, end):
    results = []
    url = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
    start_day, end_day = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    params = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'pageNo': '1',
              'tndrbidRegDtStart': start_day, 'tndrbidRegDtEnd': end_day}
    try:
        response = requests.get(url, params=params, timeout=20)
        response.encoding = response.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', response.text)
        if "<resultCode>00</resultCode>" not in clean_xml:
            return results
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        for item in root.findall('.//item'):
            title = lh_clean(item.findtext('bidnmKor'))
            matched = [kw for kw in keywords if kw in title]
            if not matched:
                continue
            region_tokens = [
                (item.findtext('zoneRstrct1') or '').strip(), (item.findtext('zoneRstrct2') or '').strip(),
                (item.findtext('zoneRstrct3') or '').strip(), (item.findtext('zoneRstrct4') or '').strip(),
            ]
            region = " ".join(filter(None, region_tokens))
            if not region_pass(region_tokens):
                continue
            results.append(to_row(
                source='LH', notice_no=item.findtext('bidNum'), title=title,
                agency=lh_clean(item.findtext('zoneHqCd')), close_dt=item.findtext('tndrdocAcptEndDtm'),
                open_dt=item.findtext('openDtm'), amount=item.findtext('fdmtlAmt'),
                region=region if region else '제한없음', keyword=','.join(matched)
            ))
    except Exception:
        pass
    return results


@st.cache_data(ttl=600, show_spinner=False)
def fetch_kogas(keywords, start, end):
    results = []
    base_url = "http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList"
    start_date, end_date = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    params = {'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500',
              'DOCDATE_START': start_date, 'DOCDATE_END': end_date}
    try:
        res = requests.get(base_url, params=params, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            return results
        root = ET.fromstring(res.text)
        for item in root.findall('.//item'):
            title = item.findtext('NOTICE_NAME') or '-'
            matched = [kw for kw in keywords if kw in title]
            if not matched:
                continue
            notice_dt = (item.findtext('NOTICE_DT') or '').replace('-', '')[:8]
            if notice_dt and not (start_date <= notice_dt <= end_date):
                continue
            results.append(to_row(
                source='가스공사', notice_no=item.findtext('NOTICE_CODE') or '-', title=title,
                agency=item.findtext('CONT_METHOD_NAME') or '-', close_dt=item.findtext('END_DT') or '-',
                open_dt='-', amount='-', region='확인불가(매뉴얼 미확인)', keyword=','.join(matched)
            ))
    except Exception:
        pass
    return results


@st.cache_data(ttl=600, show_spinner=False)
def fetch_kwater(keywords, start, end):
    results = []
    base_url = "http://apis.data.go.kr/B500001/ebid/tndr3/servcList"
    search_month = datetime.now().strftime('%Y%m')
    for kw in keywords:
        params = {'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '100',
                  '_type': 'json', 'searchDt': search_month, 'bidNm': kw}
        try:
            res = requests.get(base_url, params=params, headers=HEADERS, timeout=10)
            if res.status_code != 200:
                continue
            items = res.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])
            items = [items] if isinstance(items, dict) else (items or [])
            for it in items:
                title = it.get('tndrPblancNm', '-')
                if kw not in title:
                    continue
                results.append(to_row(
                    source='수자원공사', notice_no=it.get('tndrPbanno', '-'), title=title,
                    agency=it.get('cntrctDeptNm', '-'), close_dt=it.get('tndrPblancEnddt', '-'),
                    open_dt='-', amount='-', region='확인불가(매뉴얼 미확인)', keyword=kw
                ))
        except Exception:
            pass

    seen, dedup = set(), []
    for r in results:
        if r['공고번호'] not in seen:
            seen.add(r['공고번호'])
            dedup.append(r)
    return dedup


# =====================================================================
# 2. 사이드바 (필터)
# =====================================================================
st.sidebar.title("📡 입찰공고 통합 레이더")

today = datetime.now()
default_start = today - timedelta(days=6)

date_range = st.sidebar.date_input("검색기간 (공고/등록일 기준)", value=(default_start, today))
start_dt, end_dt = (date_range if isinstance(date_range, tuple) and len(date_range) == 2
                     else (default_start, today))
start_dt, end_dt = datetime.combine(start_dt, datetime.min.time()), datetime.combine(end_dt, datetime.min.time())

kw_text = st.sidebar.text_area("키워드 (쉼표로 구분)", value=", ".join(DEFAULT_KEYWORDS), height=80)
keywords = [k.strip() for k in kw_text.split(",") if k.strip()]

sources_selected = st.sidebar.multiselect(
    "출처기관", ["나라장터", "국방부(일반경쟁)", "국방부(공개수의)", "LH", "가스공사", "수자원공사"],
    default=["나라장터", "국방부(일반경쟁)", "국방부(공개수의)", "LH", "가스공사", "수자원공사"]
)

show_region_unknown = st.sidebar.checkbox("지역 확인불가 항목도 표시 (가스공사/수자원공사)", value=True)

run = st.sidebar.button("🔍 조회 실행", type="primary", width='stretch')

st.sidebar.caption(
    "⚠️ 가스공사 · 수자원공사는 API 매뉴얼이 없어 지역제한 필드를 확인하지 못했습니다. "
    "전체 노출하며 지역필터는 적용되지 않습니다."
)

# =====================================================================
# 3. 메인 화면
# =====================================================================
st.title("입찰공고 통합 조회")
st.caption(f"검색기간: {start_dt:%Y-%m-%d} ~ {end_dt:%Y-%m-%d}  |  키워드 {len(keywords)}개  |  지역필터: 경기도/평택/화성/전국(제한없음)")

if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()

if run:
    all_rows = []
    progress = st.progress(0, text="조회를 시작합니다...")
    steps = [
        ("나라장터", fetch_narajangter), ("국방부", fetch_d2b), ("LH", fetch_lh),
        ("가스공사", fetch_kogas), ("수자원공사", fetch_kwater),
    ]
    for i, (name, fn) in enumerate(steps, 1):
        progress.progress((i - 1) / len(steps), text=f"[{i}/{len(steps)}] {name} 조회 중...")
        try:
            all_rows.extend(fn(tuple(keywords), start_dt, end_dt))
        except Exception as e:
            st.warning(f"{name} 조회 중 오류: {e}")
    progress.progress(1.0, text="완료")

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df = df[df['출처기관'].isin(sources_selected)]
        if not show_region_unknown:
            df = df[~df['지역제한'].astype(str).str.contains('확인불가', na=False)]
    st.session_state.df = df

df = st.session_state.df

if df.empty:
    st.info("좌측에서 조건을 설정하고 **조회 실행**을 눌러주세요.")
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("총 건수", f"{len(df)}건")
    c2.metric("출처기관 수", f"{df['출처기관'].nunique()}개")
    c3.metric("지역 확인불가", f"{(df['지역제한'].astype(str).str.contains('확인불가')).sum()}건")

    st.dataframe(
        df, width='stretch', height=600,
        column_config={
            "금액(원)": st.column_config.TextColumn("금액(원)"),
            "공고명": st.column_config.TextColumn("공고명", width="large"),
        }
    )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='통합결과', index=False)
        for src in df['출처기관'].unique():
            df[df['출처기관'] == src].to_excel(writer, sheet_name=str(src)[:31], index=False)
    st.download_button("📥 엑셀로 다운로드", data=buf.getvalue(),
                        file_name=f"통합_입찰공고_{datetime.now():%Y%m%d_%H%M}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
