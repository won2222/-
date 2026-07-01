# -*- coding: utf-8 -*-
"""
통합 입찰공고 레이더 (Streamlit 웹앱)
나라장터 / 국방부 / LH / 가스공사 / 수자원공사

배포: GitHub(web_radar.py) + requirements.txt → Streamlit Cloud
"""

import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import unquote
import re
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(page_title="입찰공고 통합 레이더", layout="wide")

# =====================================================================
# 0. 공통 설정
# =====================================================================
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS     = {'User-Agent': 'Mozilla/5.0'}

DEFAULT_KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽",
                    "식물성", "부유물", "초본류", "초목류", "임목", "폐가구"]
OUR_LICENSES        = ['1226', '1227', '6786', '6770']
WASTE_LICENSE_NAMES = ['폐기물처리업', '폐기물수집운반업', '폐기물재활용업']

KWATER_DETAIL_BASE = ("https://ebid.kwater.or.kr/wq/index.do"
                       "?w2xPath=/ui/index.xml"
                       "&view=bidpblanc/bidpblancsttus/BIDBD32000002.xml"
                       "&tndrPbanno=")
KOGAS_HOME = "https://k-ebid.kogas.or.kr"
D2B_HOME   = "https://www.d2b.go.kr/"
LH_HOME    = "https://ebid.lh.or.kr/"


# =====================================================================
# 1. 필터 함수 (test_mode 인자로 ON/OFF)
# =====================================================================
REGION_FREE = ['전국', '제한없음']

def _region_token_pass(token: str) -> bool:
    token = token.strip()
    if not token: return True
    if any(f in token for f in REGION_FREE): return True
    if '평택' in token or '화성' in token: return True
    if token == '경기도': return True
    return False

def region_pass(region_text, test_mode=False) -> bool:
    if test_mode: return True
    if region_text is None: return True
    tokens = list(region_text) if isinstance(region_text, (list,tuple,set)) \
             else re.split(r'[,]', str(region_text).strip())
    return any(_region_token_pass(t) for t in tokens) if tokens else True

def license_code_pass(license_text, test_mode=False) -> bool:
    if test_mode: return True
    if not license_text: return True
    return any(code in str(license_text) for code in OUR_LICENSES)

def lh_license_pass(item, test_mode=False) -> bool:
    if test_mode: return True
    for n in range(1,11):
        slots = [lh_clean(item.findtext(f'req{n}Reqlic{m}Nm')) for m in range(1,11)]
        slots = [s for s in slots if s]
        if not slots: continue
        if not any(name in s for s in slots for name in WASTE_LICENSE_NAMES):
            return False
    return True

def lh_clean(text):
    return re.sub(r'<!\[CDATA\[|\]\]>','',text).strip() if text else ""

def format_d2b_dt(val):
    if not val or str(val).strip() in ('','-'): return '-'
    s = str(val).replace('.0','').strip()
    try:
        if len(s)>=12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
        elif len(s)>=8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return s
    except: return s

def to_row(source, notice_no, title, agency, notice_dt, close_dt, open_dt,
           amount, region, license_info, keyword, url='', extra=''):
    return {'출처기관':source,'공고번호':notice_no,'공고명':title,'수요/발주기관':agency,
            '공고일시':notice_dt,'마감일시':close_dt,'개찰일시':open_dt,'금액(원)':amount,
            '지역제한':region,'면허정보':license_info,'매칭키워드':keyword,
            '상세URL':url,'비고':extra}


# =====================================================================
# 2. 기관별 수집 함수 (캐시 10분)
# =====================================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_narajangter(keywords, start, end, test_mode):
    service_key = unquote(SERVICE_KEY)
    s_date = start.strftime("%Y%m%d0000")
    e_date = end.strftime("%Y%m%d2359")
    url_base = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'

    all_raw = []
    for kw in keywords:
        try:
            res = requests.get(url_base+'getBidPblancListInfoServcPPSSrch',
                params={'serviceKey':service_key,'numOfRows':'100','type':'json',
                        'inqryDiv':'1','inqryBgnDt':s_date,'inqryEndDt':e_date,'bidNtceNm':kw},timeout=10)
            items = res.json().get('response',{}).get('body',{}).get('items',[])
            if items:
                for it in ([items] if isinstance(items,dict) else items):
                    it['_keyword']=kw; all_raw.append(it)
        except Exception: pass

    if not all_raw: return []
    df_bids = pd.DataFrame(all_raw).drop_duplicates(subset=['bidNtceNo'])

    def fetch_detail(row):
        b_no  = row['bidNtceNo']
        b_ord = str(row.get('bidNtceOrd','000')).zfill(3)
        bp    = {'ServiceKey':service_key,'type':'json','inqryDiv':'2','bidNtceNo':b_no,'bidNtceOrd':b_ord}

        region_val = "확인불가"
        try:
            r_items = requests.get(url_base+'getBidPblancListInfoPrtcptPsblRgn',params=bp,timeout=8) \
                               .json().get('response',{}).get('body',{}).get('items',[])
            regs = [str(ri.get('prtcptPsblRgnNm','')) for ri in
                    ([r_items] if isinstance(r_items,dict) else r_items) if ri.get('prtcptPsblRgnNm')]
            region_val = ", ".join(set(regs)) if regs else "제한없음"
        except: pass

        if region_val != "확인불가" and not region_pass(region_val, test_mode):
            return None

        license_val = "확인불가"
        try:
            l_items = requests.get(url_base+'getBidPblancListInfoLicenseLimit',params=bp,timeout=8) \
                               .json().get('response',{}).get('body',{}).get('items',[])
            lics = []
            for li in ([l_items] if isinstance(l_items,dict) else l_items):
                v = li.get('lcnsLmtNm') or li.get('permsnIndstrytyList','')
                if v: lics.append(str(v))
            license_val = " / ".join(set(lics)) if lics else "제한없음"
        except: pass

        if license_val not in ("확인불가","제한없음") and not license_code_pass(license_val, test_mode):
            return None

        return to_row(
            source='나라장터', notice_no=b_no,
            title=row.get('bidNtceNm','-'), agency=row.get('dminsttNm','-'),
            notice_dt=row.get('bidNtceDate', row.get('rgstDt','-')),
            close_dt=row.get('bidClseDt','-'), open_dt=row.get('opengDt','-'),
            amount=row.get('asignBdgtAmt', row.get('bdgtAmt','-')),
            region=region_val, license_info=license_val,
            keyword=row.get('_keyword','-'), url=row.get('bidNtceDtlUrl','-'),
        )

    results = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        for r in as_completed({ex.submit(fetch_detail,row):row
                                for _,row in df_bids.reset_index(drop=True).iterrows()}):
            try:
                v = r.result()
                if v: results.append(v)
            except: pass
    return results


@st.cache_data(ttl=600, show_spinner=False)
def fetch_d2b(keywords, start, end, test_mode):
    """전체 조회 후 pblancDate(공고일자) 로컬 필터 — anmtDateBegin/End 파라미터 실제 미동작 확인"""
    results   = []
    start_day = start.strftime("%Y%m%d")
    end_day   = end.strftime("%Y%m%d")

    # 일반경쟁
    url_l = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
    url_d = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancDetail"
    for kw in keywords:
        try:
            items = requests.get(url_l,
                params={'serviceKey':SERVICE_KEY,'numOfRows':'400','_type':'json','bidNm':kw},
                headers=HEADERS,timeout=15).json() \
                .get('response',{}).get('body',{}).get('items',{}).get('item',[])
            items = [items] if isinstance(items,dict) else (items or [])
            for it in items:
                pd_dt = str(it.get('pblancDate','')).replace('.0','').strip()[:8]
                if pd_dt and not (start_day <= pd_dt <= end_day): continue
                area,open_dt,budget,g2b_no,lcns = "제한없음",it.get('opengDt','-'),it.get('budgetAmount',0),None,""
                try:
                    det = requests.get(url_d,headers=HEADERS,timeout=8,
                        params={'serviceKey':SERVICE_KEY,'_type':'json',
                                'pblancNo':it.get('pblancNo'),'pblancOdr':it.get('pblancOdr'),
                                'demandYear':it.get('demandYear'),'orntCode':it.get('orntCode'),
                                'dcsNo':it.get('dcsNo')}).json() \
                        .get('response',{}).get('body',{}).get('item',{})
                    area=det.get('areaLmttList') or "제한없음"
                    open_dt=det.get('opengDt') or open_dt
                    budget=det.get('budgetAmount') or budget
                    g2b_no=det.get('g2bPblancNo'); lcns=det.get('lcnsLmttList') or "제한없음"
                except: pass
                if not region_pass(area,test_mode): continue
                if lcns not in ("","제한없음") and not license_code_pass(lcns,test_mode): continue
                results.append(to_row(
                    source='국방부(일반경쟁)', notice_no=g2b_no or it.get('pblancNo','-'),
                    title=it.get('bidNm',''), agency=it.get('ornt','-'),
                    notice_dt=format_d2b_dt(it.get('pblancDate','-')),
                    close_dt=format_d2b_dt(it.get('biddocPresentnClosDt','-')),
                    open_dt=format_d2b_dt(open_dt), amount=budget,
                    region=area, license_info=lcns, keyword=kw, url=D2B_HOME,
                ))
        except: pass

    # 공개수의
    url_pl = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList"
    url_pd = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanDetail"
    for kw in keywords:
        try:
            items = requests.get(url_pl,
                params={'serviceKey':SERVICE_KEY,'numOfRows':'400','_type':'json','othbcNtatNm':kw},
                headers=HEADERS,timeout=15).json() \
                .get('response',{}).get('body',{}).get('items',{}).get('item',[])
            items = [items] if isinstance(items,dict) else (items or [])
            for it in items:
                plan_dt = str(it.get('ntatPlanDate','')).replace('.0','').strip()[:8]
                if plan_dt and not (start_day <= plan_dt <= end_day): continue
                area,open_dt,budget,g2b_no,lcns = "제한없음",it.get('opengDt','-'),it.get('budgetAmount',0),None,""
                try:
                    det = requests.get(url_pd,headers=HEADERS,timeout=8,
                        params={'serviceKey':SERVICE_KEY,'_type':'json',
                                'pblancNo':it.get('pblancNo'),'pblancOdr':it.get('pblancOdr'),
                                'demandYear':it.get('demandYear'),'orntCode':it.get('orntCode'),
                                'dcsNo':it.get('dcsNo'),'iemNo':it.get('iemNo'),
                                'ntatPlanDate':it.get('ntatPlanDate')}).json() \
                        .get('response',{}).get('body',{}).get('item',{})
                    area=det.get('areaLmttList') or "제한없음"
                    open_dt=det.get('opengDt') or open_dt
                    budget=det.get('budgetAmount') or budget
                    g2b_no=det.get('g2bPblancNo'); lcns=det.get('lcnsLmttList') or "제한없음"
                except: pass
                if not region_pass(area,test_mode): continue
                if lcns not in ("","제한없음") and not license_code_pass(lcns,test_mode): continue
                results.append(to_row(
                    source='국방부(공개수의)', notice_no=g2b_no or it.get('pblancNo','-'),
                    title=it.get('othbcNtatNm',''), agency=it.get('ornt','-'),
                    notice_dt='-',
                    close_dt=format_d2b_dt(it.get('prqudoPresentnClosDt','-')),
                    open_dt=format_d2b_dt(open_dt), amount=budget,
                    region=area, license_info=lcns, keyword=kw, url=D2B_HOME,
                    extra='⚠️개찰예정일 기준 필터(공고일자 파라미터 없음)',
                ))
        except: pass

    seen, dedup = set(), []
    for r in results:
        key=(r['출처기관'],r['공고번호'])
        if key not in seen: seen.add(key); dedup.append(r)
        else:
            for d in dedup:
                if (d['출처기관'],d['공고번호'])==key and r['매칭키워드'] not in d['매칭키워드']:
                    d['매칭키워드']+=f",{r['매칭키워드']}"
    return dedup


@st.cache_data(ttl=600, show_spinner=False)
def fetch_lh(keywords, start, end, test_mode):
    results   = []
    url       = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
    start_day = start.strftime("%Y%m%d"); end_day = end.strftime("%Y%m%d")
    try:
        response = requests.get(url,
            params={'serviceKey':SERVICE_KEY,'numOfRows':'500','pageNo':'1',
                    'tndrbidRegDtStart':start_day,'tndrbidRegDtEnd':end_day},timeout=20)
        response.encoding = response.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>','',response.text)
        if "<resultCode>00</resultCode>" not in clean_xml: return results
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        for item in root.findall('.//item'):
            title = lh_clean(item.findtext('bidnmKor'))
            matched = [kw for kw in keywords if kw in title]
            if not matched: continue
            rt = [(item.findtext(f'zoneRstrct{n}') or '').strip() for n in range(1,5)]
            region = " ".join(filter(None, rt))
            if not region_pass(rt, test_mode): continue
            if not lh_license_pass(item, test_mode): continue
            lic = "/".join(sorted(set(
                lh_clean(item.findtext(f'req{n}Reqlic{m}Nm'))
                for n in range(1,11) for m in range(1,11)
                if lh_clean(item.findtext(f'req{n}Reqlic{m}Nm'))
            ))) or '제한없음'
            results.append(to_row(
                source='LH', notice_no=item.findtext('bidNum'), title=title,
                agency=lh_clean(item.findtext('zoneHqCd')),
                notice_dt=item.findtext('tndrbidRegDt'),
                close_dt=item.findtext('tndrdocAcptEndDtm'),
                open_dt=item.findtext('openDtm'), amount=item.findtext('fdmtlAmt'),
                region=region if region else '제한없음',
                license_info=lic, keyword=','.join(matched), url=LH_HOME,
            ))
    except: pass
    return results


@st.cache_data(ttl=600, show_spinner=False)
def fetch_kogas(keywords, start, end):
    results = []
    try:
        res = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList",
            params={'serviceKey':SERVICE_KEY,'pageNo':'1','numOfRows':'500',
                    'DOCDATE_START':start.strftime("%Y%m%d"),
                    'DOCDATE_END':end.strftime("%Y%m%d")},
            headers=HEADERS, timeout=15)
        if res.status_code!=200: return results
        sd = start.strftime("%Y%m%d"); ed = end.strftime("%Y%m%d")
        for item in ET.fromstring(res.text).findall('.//item'):
            title = item.findtext('NOTICE_NAME') or '-'
            matched = [kw for kw in keywords if kw in title]
            if not matched: continue
            nd = (item.findtext('NOTICE_DT') or '').replace('-','')[:8]
            if nd and not (sd<=nd<=ed): continue
            results.append(to_row(
                source='가스공사', notice_no=item.findtext('NOTICE_CODE') or '-', title=title,
                agency=item.findtext('CONT_METHOD_NAME') or '-',
                notice_dt=item.findtext('NOTICE_DT') or '-',
                close_dt=item.findtext('END_DT') or '-', open_dt='-', amount='-',
                region='확인불가', license_info='확인불가',
                keyword=','.join(matched), url=KOGAS_HOME,
            ))
    except: pass
    return results


@st.cache_data(ttl=600, show_spinner=False)
def fetch_kwater(keywords):
    results = []
    search_month = datetime.now().strftime('%Y%m')
    for kw in keywords:
        try:
            items = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList",
                params={'serviceKey':SERVICE_KEY,'pageNo':'1','numOfRows':'100',
                        '_type':'json','searchDt':search_month,'bidNm':kw},
                headers=HEADERS, timeout=10).json() \
                .get('response',{}).get('body',{}).get('items',{}).get('item',[])
            items = [items] if isinstance(items,dict) else (items or [])
            for it in items:
                title = it.get('tndrPblancNm','-')
                if kw not in title: continue
                results.append(to_row(
                    source='수자원공사', notice_no=it.get('tndrPbanno','-'), title=title,
                    agency=it.get('cntrctDeptNm','-'), notice_dt='-',
                    close_dt=it.get('tndrPblancEnddt','-'), open_dt='-', amount='-',
                    region='확인불가', license_info='확인불가', keyword=kw,
                    url=(KWATER_DETAIL_BASE+str(it.get('tndrPbanno',''))) if it.get('tndrPbanno') else '-',
                ))
        except: pass
    seen, dedup = set(), []
    for r in results:
        if r['공고번호'] not in seen: seen.add(r['공고번호']); dedup.append(r)
    return dedup


# =====================================================================
# 3. 사이드바
# =====================================================================
st.sidebar.title("📡 입찰공고 통합 레이더")

today = datetime.now()
date_range = st.sidebar.date_input("검색기간", value=(today-timedelta(days=6), today))
start_dt, end_dt = (date_range if isinstance(date_range,tuple) and len(date_range)==2
                    else (today-timedelta(days=6), today))
start_dt = datetime.combine(start_dt, datetime.min.time())
end_dt   = datetime.combine(end_dt,   datetime.min.time())

kw_text  = st.sidebar.text_area("키워드 (쉼표 구분)", value=", ".join(DEFAULT_KEYWORDS), height=90)
keywords = tuple(k.strip() for k in kw_text.split(",") if k.strip())

sources  = st.sidebar.multiselect("출처기관",
    ["나라장터","국방부(일반경쟁)","국방부(공개수의)","LH","가스공사","수자원공사"],
    default=["나라장터","국방부(일반경쟁)","국방부(공개수의)","LH","가스공사","수자원공사"])

# ── 테스트 모드 토글 ──
test_mode = st.sidebar.toggle("🧪 테스트 모드 (지역·면허 필터 OFF)", value=True)

st.sidebar.caption(
    f"{'🔴 필터 OFF — 전체 결과 노출 중' if test_mode else '🟢 필터 ON — 경기도/평택/화성/전국 + 면허코드 적용'}\n\n"
    f"🪪 면허코드: {OUR_LICENSES}\n"
    f"LH 면허명: {WASTE_LICENSE_NAMES}\n\n"
    "⚠️ 가스공사·수자원공사는 지역·면허 필드 없어 항상 전체 노출"
)

run = st.sidebar.button("🔍 조회 실행", type="primary", use_container_width=True)

# =====================================================================
# 4. 메인 화면
# =====================================================================
st.title("입찰공고 통합 조회")
st.caption(f"{'🧪 테스트 모드 (필터 OFF)' if test_mode else '✅ 실운영 모드 (필터 ON)'} │ "
           f"{start_dt:%Y-%m-%d} ~ {end_dt:%Y-%m-%d} │ 키워드 {len(keywords)}개")

if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()

if run:
    all_rows = []
    steps = [
        ("나라장터",       lambda: fetch_narajangter(keywords, start_dt, end_dt, test_mode)),
        ("국방부",         lambda: fetch_d2b(keywords, start_dt, end_dt, test_mode)),
        ("LH",            lambda: fetch_lh(keywords, start_dt, end_dt, test_mode)),
        ("가스공사",       lambda: fetch_kogas(keywords, start_dt, end_dt)),
        ("수자원공사",     lambda: fetch_kwater(keywords)),
    ]
    prog = st.progress(0, text="조회를 시작합니다...")
    for i, (name, fn) in enumerate(steps, 1):
        prog.progress((i-1)/len(steps), text=f"[{i}/{len(steps)}] {name} 조회 중...")
        try:
            all_rows.extend(fn())
        except Exception as e:
            st.warning(f"{name} 오류: {e}")
    prog.progress(1.0, text="완료")

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df = df[df['출처기관'].isin(sources)]
    st.session_state.df = df

df = st.session_state.df

if df.empty:
    st.info("좌측에서 조건을 설정하고 **조회 실행**을 눌러주세요.")
else:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("총 건수", f"{len(df)}건")
    c2.metric("출처기관 수", f"{df['출처기관'].nunique()}개")
    c3.metric("지역 확인불가", f"{df['지역제한'].astype(str).str.contains('확인불가').sum()}건")
    c4.metric("면허 확인불가", f"{df['면허정보'].astype(str).str.contains('확인불가').sum()}건")

    st.dataframe(df, use_container_width=True, height=600,
        column_config={
            "공고명":   st.column_config.TextColumn("공고명", width="large"),
            "금액(원)": st.column_config.TextColumn("금액(원)"),
            "면허정보": st.column_config.TextColumn("면허정보", width="medium"),
            "상세URL":  st.column_config.LinkColumn("상세URL", display_text="열기"),
        })

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='통합결과', index=False)
        for src in df['출처기관'].unique():
            df[df['출처기관']==src].to_excel(writer, sheet_name=str(src)[:31], index=False)
    st.download_button("📥 엑셀로 다운로드", data=buf.getvalue(),
        file_name=f"통합_입찰공고_{datetime.now():%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
