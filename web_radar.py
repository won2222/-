# -*- coding: utf-8 -*-
"""
폐기물 입찰 레이더 ── v2.7
변경이력:
  v2.0  5개 기관 통합
  v2.6  국방부 원본 로직 반영 (service_key 언더스코어, 날짜필터 없음)
  v2.7  흰화면 오류 수정 (구글폰트/복잡CSS 제거), 누락 함수 복구
"""
import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import unquote
import re, io
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="SWEEP · 입찰공고 통합 수집",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 최소 CSS (구글폰트 제거 → 흰화면 방지) ──
st.markdown("""
<style>
[data-testid="stSidebar"] { background-color: #1e2235; }
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div { color: #dde3f0 !important; }
.stButton > button {
    background: #2563eb !important; color: white !important;
    border: none !important; font-weight: 600 !important;
}
.stButton > button:hover { background: #1d4ed8 !important; }
[data-testid="stDownloadButton"] button {
    border: 1px solid #2563eb !important; color: #2563eb !important;
    background: white !important;
}
</style>
""", unsafe_allow_html=True)

# =====================================================================
# 0. 공통 설정
# =====================================================================
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS     = {'User-Agent': 'Mozilla/5.0'}
VERSION     = "v2.9"
TODAY       = datetime.now()

DEFAULT_KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽",
                    "식물성", "부유물", "초본류", "초목류", "임목", "폐가구"]
# 기본값 - 사이드바에서 사용자가 편집 가능
DEFAULT_LICENSES     = ['1226', '1227', '6786', '6770']
DEFAULT_LH_LICENSES  = ['폐기물처리업', '폐기물수집운반업', '폐기물재활용업']
# 런타임 값 (사이드바에서 덮어씀)
OUR_LICENSES        = DEFAULT_LICENSES
WASTE_LICENSE_NAMES = DEFAULT_LH_LICENSES
KWATER_DETAIL_BASE  = "https://ebid.kwater.or.kr/wq/index.do?w2xPath=/ui/index.xml&view=bidpblanc/bidpblancsttus/BIDBD32000002.xml&tndrPbanno="
KOGAS_HOME = "https://k-ebid.kogas.or.kr"
D2B_HOME   = "https://www.d2b.go.kr/"
LH_HOME    = "https://ebid.lh.or.kr/"

# =====================================================================
# 1. 공통 함수
# =====================================================================
def _region_token_pass(token):
    token = token.strip()
    if not token: return True
    if any(f in token for f in ['전국', '제한없음']): return True
    if '평택' in token or '화성' in token: return True
    if token == '경기도': return True
    return False

def region_pass(region_text, test_mode=False):
    if test_mode: return True
    if region_text is None: return True
    tokens = list(region_text) if isinstance(region_text, (list, tuple, set)) \
             else re.split(r'[,]', str(region_text).strip())
    return any(_region_token_pass(t) for t in tokens) if tokens else True

def license_code_pass(license_text, test_mode=False):
    if test_mode: return True
    if not license_text: return True
    return any(code in str(license_text) for code in OUR_LICENSES)

def lh_clean(text):
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip() if text else ""

def lh_license_pass(item, test_mode=False):
    if test_mode: return True
    for n in range(1, 11):
        slots = [lh_clean(item.findtext(f'req{n}Reqlic{m}Nm')) for m in range(1, 11)]
        slots = [s for s in slots if s]
        if not slots: continue
        if not any(name in s for s in slots for name in WASTE_LICENSE_NAMES):
            return False
    return True

def format_d2b_dt(val):
    if not val or str(val).strip() in ('', '-'): return '-'
    s = str(val).replace('.0', '').strip()
    try:
        if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
        elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return s
    except: return s

def to_row(source, notice_no, title, agency, notice_dt, close_dt, open_dt,
           amount, region, license_info, keyword, url='', extra=''):
    return {
        '출처기관': source, '공고번호': notice_no, '공고명': title,
        '수요/발주기관': agency, '공고일시': notice_dt, '마감일시': close_dt,
        '개찰일시': open_dt, '금액(원)': amount, '지역제한': region,
        '면허정보': license_info, '매칭키워드': keyword, '상세URL': url, '비고': extra,
    }

# =====================================================================
# 2. 나라장터
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
            res = requests.get(url_base + 'getBidPblancListInfoServcPPSSrch',
                params={'serviceKey': service_key, 'numOfRows': '100', 'type': 'json',
                        'inqryDiv': '1', 'inqryBgnDt': s_date, 'inqryEndDt': e_date,
                        'bidNtceNm': kw}, timeout=10)
            items = res.json().get('response', {}).get('body', {}).get('items', [])
            if items:
                for it in ([items] if isinstance(items, dict) else items):
                    it['_keyword'] = kw
                    all_raw.append(it)
        except: pass

    if not all_raw: return []
    df_bids = pd.DataFrame(all_raw).drop_duplicates(subset=['bidNtceNo'])

    def call_api(url, params, retries=2):
        """API 호출 + 실패 시 재시도 (속도 초과 대응)"""
        for attempt in range(retries):
            try:
                res = requests.get(url, params=params, timeout=10)
                if res.status_code == 200:
                    return res.json()
            except: pass
            import time; time.sleep(0.3 * (attempt + 1))
        return {}

    def fetch_detail(row):
        b_no  = row['bidNtceNo']
        b_ord = str(row.get('bidNtceOrd', '000')).zfill(3)
        bp = {'ServiceKey': service_key, 'type': 'json', 'inqryDiv': '2',
              'bidNtceNo': b_no, 'bidNtceOrd': b_ord}

        # 지역 조회
        region_val = "⚠️조회실패"
        try:
            r_items = call_api(url_base + 'getBidPblancListInfoPrtcptPsblRgn', bp) \
                .get('response', {}).get('body', {}).get('items', [])
            regs = [str(ri.get('prtcptPsblRgnNm', '')) for ri in
                    ([r_items] if isinstance(r_items, dict) else r_items)
                    if ri.get('prtcptPsblRgnNm')]
            region_val = ", ".join(set(regs)) if regs else "제한없음"
        except: pass

        # 지역 필터: 조회 성공한 경우만 필터 적용, 실패는 포함하되 표시
        if "⚠️조회실패" not in region_val and not region_pass(region_val, test_mode):
            return None

        # 면허 조회
        license_val = "⚠️조회실패"
        try:
            l_items = call_api(url_base + 'getBidPblancListInfoLicenseLimit', bp) \
                .get('response', {}).get('body', {}).get('items', [])
            lics = []
            for li in ([l_items] if isinstance(l_items, dict) else l_items):
                v = li.get('lcnsLmtNm') or li.get('permsnIndstrytyList', '')
                if v: lics.append(str(v))
            license_val = " / ".join(set(lics)) if lics else "제한없음"
        except: pass

        if license_val not in ("⚠️조회실패", "제한없음") and not license_code_pass(license_val, test_mode):
            return None

        return to_row(
            source='나라장터', notice_no=b_no,
            title=row.get('bidNtceNm', '-'), agency=row.get('dminsttNm', '-'),
            notice_dt=row.get('bidNtceDate', row.get('rgstDt', '-')),
            close_dt=row.get('bidClseDt', '-'), open_dt=row.get('opengDt', '-'),
            amount=row.get('asignBdgtAmt', row.get('bdgtAmt', '-')),
            region=region_val, license_info=license_val,
            keyword=row.get('_keyword', '-'), url=row.get('bidNtceDtlUrl', '-'),
        )

    results = []
    # 스레드 8개로 제한 (API 초당 30건 제한 대응)
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in as_completed({ex.submit(fetch_detail, row): row
                                for _, row in df_bids.reset_index(drop=True).iterrows()}):
            try:
                v = r.result()
                if v: results.append(v)
            except: pass
    return results

# =====================================================================
# 3. 국방부 ── 원본(국방부_필터링_완성_최종.py) 로직 100% 반영
#    service_key(언더스코어), 일반입찰 날짜필터 없음
# =====================================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_d2b(keywords, start, end, test_mode):
    results   = []
    today_dt  = TODAY
    d2b_start = (today_dt - timedelta(days=10)).strftime("%Y%m%d")
    d2b_end   = (today_dt + timedelta(days=20)).strftime("%Y%m%d")
    target_areas = ["경기도", "평택시", "화성시", "제한없음", "전국"]

    api_configs = [
        {'type': '일반입찰',
         'list_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList',
         'det_url':  'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancDetail',
         'source': '국방부(일반경쟁)'},
        {'type': '공개수의',
         'list_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList',
         'det_url':  'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanDetail',
         'source': '국방부(공개수의)'},
    ]

    for config in api_configs:
        params = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
        if config['type'] == '공개수의':
            params.update({'prqudoPresentnClosDateBegin': d2b_start,
                           'prqudoPresentnClosDateEnd':   d2b_end})
        try:
            res = requests.get(config['list_url'], params=params, headers=HEADERS, timeout=15)
            if res.status_code != 200: continue
            items = res.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])
            items = [items] if isinstance(items, dict) else items

            for it in items:
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                matched_kw = [kw for kw in keywords if kw in bid_nm]
                if not matched_kw: continue

                p_no    = it.get('pblancNo') or ''
                d_year  = str(it.get('demandYear', ''))
                d_no    = str(it.get('dcsNo', ''))
                p_alpha = "".join([c for c in p_no if c.isalpha()])
                combined_g2b = f"{d_year}{p_alpha}{d_no}"

                p_det = {
                    'service_key': SERVICE_KEY,      # ★ 원본 그대로 언더스코어
                    'pblancNo':    p_no,
                    'pblancOdr':   str(it.get('pblancOdr', '1')).split('.')[0],
                    'demandYear':  d_year,
                    'orntCode':    it.get('orntCode'),
                    'dcsNo':       d_no,
                    '_type':       'json',
                }
                if config['type'] == '공개수의':
                    p_det.update({'ntatPlanDate': it.get('ntatPlanDate'),
                                  'iemNo':        it.get('iemNo')})

                area, budget = "제한없음", 0
                try:
                    det_res  = requests.get(config['det_url'], params=p_det,
                                            headers=HEADERS, timeout=5).json()
                    det_data = det_res.get('response', {}).get('body', {}).get('item', {})
                    if isinstance(det_data, dict):
                        area         = det_data.get('areaLmttList') or "제한없음"
                        combined_g2b = det_data.get('g2bPblancNo') or combined_g2b
                        budget       = (det_data.get('budgetAmount') or
                                        it.get('asignBdgtAmt') or
                                        it.get('budgetAmount') or 0)
                except: pass

                status = it.get('progrsSttus') or "진행중"
                if not ("진행중" in status or status == ""): continue
                if not test_mode and not any(t in area for t in target_areas): continue
                if test_mode or any(t in area for t in target_areas):
                    pass
                else:
                    continue

                results.append(to_row(
                    source=config['source'],
                    notice_no=combined_g2b or p_no or '-',
                    title=bid_nm, agency=it.get('ornt', '-'),
                    notice_dt=format_d2b_dt(it.get('pblancDate', '-')),
                    close_dt=format_d2b_dt(
                        it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')),
                    open_dt=format_d2b_dt(it.get('opengDt', '-')),
                    amount=int(pd.to_numeric(budget, errors='coerce') or 0),
                    region=area, license_info='미조회',
                    keyword=','.join(matched_kw), url=D2B_HOME,
                ))
        except: pass

    seen, dedup = set(), []
    for r in results:
        key = (r['출처기관'], r['공고번호'])
        if key not in seen:
            seen.add(key); dedup.append(r)
        else:
            for d in dedup:
                if (d['출처기관'], d['공고번호']) == key and r['매칭키워드'] not in d['매칭키워드']:
                    d['매칭키워드'] += f",{r['매칭키워드']}"
    return dedup

# =====================================================================
# 4. LH
# =====================================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_lh(keywords, start, end, test_mode):
    results = []
    try:
        response = requests.get(
            "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev",
            params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'pageNo': '1',
                    'tndrbidRegDtStart': start.strftime("%Y%m%d"),
                    'tndrbidRegDtEnd':   end.strftime("%Y%m%d")}, timeout=20)
        response.encoding = response.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*?>', '', response.text)
        if "<resultCode>00</resultCode>" not in clean_xml: return results
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        for item in root.findall('.//item'):
            title = lh_clean(item.findtext('bidnmKor'))
            matched = [kw for kw in keywords if kw in title]
            if not matched: continue
            rt = [(item.findtext(f'zoneRstrct{n}') or '').strip() for n in range(1, 5)]
            region = " ".join(filter(None, rt))
            if not region_pass(rt, test_mode): continue
            if not lh_license_pass(item, test_mode): continue
            lic = "/".join(sorted(set(
                lh_clean(item.findtext(f'req{n}Reqlic{m}Nm'))
                for n in range(1, 11) for m in range(1, 11)
                if lh_clean(item.findtext(f'req{n}Reqlic{m}Nm'))
            ))) or '제한없음'
            results.append(to_row(
                source='LH', notice_no=item.findtext('bidNum'), title=title,
                agency=lh_clean(item.findtext('zoneHqCd')),
                notice_dt=item.findtext('tndrbidRegDt'),
                close_dt=item.findtext('tndrdocAcptEndDtm'),
                open_dt=item.findtext('openDtm'), amount=item.findtext('fdmtlAmt'),
                region=region if region else '제한없음', license_info=lic,
                keyword=','.join(matched), url=LH_HOME,
            ))
    except: pass
    return results

# =====================================================================
# 5. 가스공사
# =====================================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_kogas(keywords, start, end):
    results = []
    try:
        res = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList",
            params={'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500',
                    'DOCDATE_START': start.strftime("%Y%m%d"),
                    'DOCDATE_END':   end.strftime("%Y%m%d")},
            headers=HEADERS, timeout=15)
        if res.status_code != 200: return results
        sd = start.strftime("%Y%m%d"); ed = end.strftime("%Y%m%d")
        for item in ET.fromstring(res.text).findall('.//item'):
            title = item.findtext('NOTICE_NAME') or '-'
            matched = [kw for kw in keywords if kw in title]
            if not matched: continue
            nd = (item.findtext('NOTICE_DT') or '').replace('-', '')[:8]
            if nd and not (sd <= nd <= ed): continue
            results.append(to_row(
                source='가스공사', notice_no=item.findtext('NOTICE_CODE') or '-',
                title=title, agency=item.findtext('CONT_METHOD_NAME') or '-',
                notice_dt=item.findtext('NOTICE_DT') or '-',
                close_dt=item.findtext('END_DT') or '-', open_dt='-', amount='-',
                region='확인불가', license_info='확인불가',
                keyword=','.join(matched), url=KOGAS_HOME,
            ))
    except: pass
    return results

# =====================================================================
# 6. 수자원공사
# =====================================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_kwater(keywords):
    results = []
    search_month = TODAY.strftime('%Y%m')
    for kw in keywords:
        try:
            items = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList",
                params={'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '100',
                        '_type': 'json', 'searchDt': search_month, 'bidNm': kw},
                headers=HEADERS, timeout=10).json() \
                .get('response', {}).get('body', {}).get('items', {}).get('item', [])
            items = [items] if isinstance(items, dict) else (items or [])
            for it in items:
                title = it.get('tndrPblancNm', '-')
                if kw not in title: continue
                results.append(to_row(
                    source='수자원공사', notice_no=it.get('tndrPbanno', '-'),
                    title=title, agency=it.get('cntrctDeptNm', '-'),
                    notice_dt='-', close_dt=it.get('tndrPblancEnddt', '-'),
                    open_dt='-', amount='-', region='확인불가', license_info='확인불가',
                    keyword=kw,
                    url=(KWATER_DETAIL_BASE + str(it.get('tndrPbanno', '')))
                        if it.get('tndrPbanno') else '-',
                ))
        except: pass
    seen, dedup = set(), []
    for r in results:
        if r['공고번호'] not in seen:
            seen.add(r['공고번호']); dedup.append(r)
    return dedup

# =====================================================================
# 7. 사이드바
# =====================================================================
with st.sidebar:
    st.markdown(f"## 🧹 SWEEP\n**{VERSION}** · 5개 기관 입찰공고 통합 수집")
    st.divider()

    st.markdown("**📅 검색기간** (나라장터·LH·가스공사)")
    date_range = st.date_input("기간", value=(TODAY - timedelta(days=6), TODAY),
                               label_visibility="collapsed")
    start_dt, end_dt = (date_range if isinstance(date_range, tuple) and len(date_range) == 2
                        else (TODAY - timedelta(days=6), TODAY))
    start_dt = datetime.combine(start_dt, datetime.min.time())
    end_dt   = datetime.combine(end_dt,   datetime.min.time())

    st.caption("🏛 국방부: 오늘-10일 ~ 오늘+20일 마감 기준")

    st.markdown("**🎯 키워드**")
    kw_text  = st.text_area("키워드", value=", ".join(DEFAULT_KEYWORDS),
                             height=90, label_visibility="collapsed")
    keywords = tuple(k.strip() for k in kw_text.split(",") if k.strip())

    st.markdown("**🪪 면허코드** (나라장터·국방부)")
    lic_text = st.text_area("면허코드",
                             value=", ".join(DEFAULT_LICENSES),
                             height=55, label_visibility="collapsed",
                             help="쉼표로 구분. 예: 1226, 1227, 6786, 6770")
    OUR_LICENSES = [l.strip() for l in lic_text.split(",") if l.strip()]

    st.markdown("**🪪 LH 면허명** (LH 전용)")
    lh_lic_text = st.text_area("LH면허명",
                                value=", ".join(DEFAULT_LH_LICENSES),
                                height=55, label_visibility="collapsed",
                                help="쉼표로 구분. LH는 면허명(텍스트)으로 매칭")
    WASTE_LICENSE_NAMES = [l.strip() for l in lh_lic_text.split(",") if l.strip()]

    st.markdown("**🏛️ 출처기관**")
    sources  = st.multiselect("기관",
        ["나라장터", "국방부(일반경쟁)", "국방부(공개수의)", "LH", "가스공사", "수자원공사"],
        default=["나라장터", "국방부(일반경쟁)", "국방부(공개수의)", "LH", "가스공사", "수자원공사"],
        label_visibility="collapsed")

    test_mode = st.toggle("🧪 테스트 모드 (필터 OFF)", value=True)

    st.divider()
    st.caption(
        f"{'🔴 필터 OFF — 전체 노출' if test_mode else '🟢 필터 ON'}\n\n"
        f"📍 지역: 경기도·평택·화성·전국\n"
        f"🪪 면허코드: {', '.join(OUR_LICENSES)}\n"
        f"⚠️ 가스공사·수자원공사 지역·면허 미지원"
    )
    st.markdown("")
    run = st.button("🔍 조회 실행", use_container_width=True)

# =====================================================================
# 8. 메인 화면
# =====================================================================
st.title("🧹 SWEEP — 입찰공고 통합 수집")
st.caption(
    f"{VERSION} · 나라장터/국방부/LH/가스공사/수자원공사 · "
    f"공고일 {start_dt:%m/%d}~{end_dt:%m/%d} · "
    f"{'🧪 테스트 모드(필터 OFF)' if test_mode else '✅ 실운영 모드(필터 ON)'}"
)

if "df"     not in st.session_state: st.session_state.df     = pd.DataFrame()
if "errors" not in st.session_state: st.session_state.errors = {}

if run:
    errors, all_rows = {}, []

    def run_agency(name, fn):
        try:    return name, fn(), None
        except Exception as e: return name, [], str(e)

    steps = {
        "나라장터":   lambda: fetch_narajangter(keywords, start_dt, end_dt, test_mode),
        "국방부":     lambda: fetch_d2b(keywords, start_dt, end_dt, test_mode),
        "LH":        lambda: fetch_lh(keywords, start_dt, end_dt, test_mode),
        "가스공사":   lambda: fetch_kogas(keywords, start_dt, end_dt),
        "수자원공사": lambda: fetch_kwater(keywords),
    }

    prog      = st.progress(0, text="탐지 중...")
    cols      = st.columns(5)
    status_el = {n: c.empty() for n, c in zip(steps, cols)}
    for n in steps:
        status_el[n].markdown(f"**{n}**\n\n⏳")

    done = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(run_agency, n, fn): n for n, fn in steps.items()}
        for future in as_completed(futures):
            name, rows, err = future.result()
            done += 1
            prog.progress(done / len(steps), text=f"{name} 완료 ({done}/{len(steps)})")
            if err:
                errors[name] = err
                status_el[name].markdown(f"**{name}**\n\n❌ 오류")
            else:
                all_rows.extend(rows)
                status_el[name].markdown(f"**{name}**\n\n✅ {len(rows)}건")

    prog.progress(1.0, text="완료")
    df = pd.DataFrame(all_rows)
    if not df.empty:
        df = df[df['출처기관'].apply(
            lambda s: any(s == src or s.startswith(src.split('(')[0]) for src in sources))]
    st.session_state.df     = df
    st.session_state.errors = errors

df     = st.session_state.df
errors = st.session_state.get("errors", {})

for name, err in errors.items():
    st.warning(f"⚠️ {name}: {err}")

if df.empty:
    st.info("👈 왼쪽에서 조건을 설정하고 **조회 실행**을 눌러주세요.")
else:
    fail_mask = df['지역제한'].astype(str).str.contains('⚠️조회실패', na=False)
    fail_cnt  = fail_mask.sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 공고", f"{len(df)}건")
    c2.metric("출처기관", f"{df['출처기관'].nunique()}개")
    c3.metric("지역조회 실패", f"{fail_cnt}건",
              help="API 속도 제한으로 지역 조회에 실패한 공고. 실제 지역 제한이 걸려있을 수 있으니 직접 확인 필요.")
    c4.metric("면허 미확인",
              f"{df['면허정보'].astype(str).str.contains('⚠️조회실패|미조회', na=False).sum()}건")

    if fail_cnt > 0:
        hide_fail = st.checkbox(
            f"⚠️ 지역조회 실패 {fail_cnt}건 숨기기 (직접 확인 필요한 공고)",
            value=False,
            help="나라장터 API 초당 제한으로 지역 조회에 실패했습니다. 충청북도 제천시처럼 "
                 "우리 지역이 아닌 제한이 걸려있을 수 있으니 체크 후 나라장터에서 직접 확인하세요."
        )
        if hide_fail:
            df = df[~fail_mask]
            st.caption(f"조회실패 {fail_cnt}건 제외 → {len(df)}건 표시 중")

    # 금액 3자리 콤마 포맷 적용
    df_display = df.copy()
    def fmt_amount(v):
        try:
            n = int(float(str(v).replace(',', '').replace('원', '').strip()))
            return f"{n:,}원" if n > 0 else '-'
        except:
            return str(v) if v and str(v) not in ('nan', 'None', '-') else '-'
    df_display['금액(원)'] = df_display['금액(원)'].apply(fmt_amount)

    st.divider()
    st.dataframe(df_display, use_container_width=True, height=540,
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
            df[df['출처기관'] == src].to_excel(writer, sheet_name=str(src)[:31], index=False)
    st.download_button("📥 엑셀 다운로드", data=buf.getvalue(),
        file_name=f"입찰레이더_{TODAY:%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
