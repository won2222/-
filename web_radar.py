# -*- coding: utf-8 -*-
"""
폐기물 입찰 레이더 (BID RADAR) ── v2.2 (2026-07-01)
나라장터 / 국방부 / LH / 가스공사 / 수자원공사

[변경 이력]
v2.0  5개 기관 통합 / 국방부 bidNm 버그 수정
v2.1  버전 표시 및 조회 기준 명문화
v2.2  UI 전면 개편 / 국방부 fetch_d2b 유실 복구 / 5개 기관 병렬 실행으로 속도 개선
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

st.set_page_config(
    page_title="폐기물 입찰 레이더",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 디자인 CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Sans KR', 'Malgun Gothic', sans-serif; }

/* 배경 */
.stApp { background: #0d1117; color: #e6edf3; }
[data-testid="stSidebar"] { background: #161b22; border-right: 1px solid #30363d; }

/* 헤더 배너 */
.radar-header {
    background: linear-gradient(135deg, #0d1117 0%, #1a2332 50%, #0d1117 100%);
    border: 1px solid #21d4fd33;
    border-radius: 12px;
    padding: 28px 36px 20px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;
}
.radar-header::before {
    content: "";
    position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    background: radial-gradient(ellipse at 70% 50%, #21d4fd0d 0%, transparent 70%);
}
.radar-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 28px; font-weight: 500;
    color: #21d4fd; letter-spacing: 2px;
    margin: 0 0 4px;
}
.radar-sub { font-size: 12px; color: #7d8590; letter-spacing: 1px; margin: 0; }
.radar-ver {
    position: absolute; top: 20px; right: 24px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px; color: #3fb95033;
    background: #3fb95011; padding: 3px 10px;
    border-radius: 20px; border: 1px solid #3fb95033;
}

/* 메트릭 카드 */
.metric-row { display: flex; gap: 12px; margin-bottom: 20px; }
.metric-card {
    flex: 1; background: #161b22;
    border: 1px solid #30363d; border-radius: 10px;
    padding: 16px 20px;
}
.metric-card.highlight { border-color: #21d4fd44; }
.metric-label { font-size: 11px; color: #7d8590; letter-spacing: 0.5px; margin-bottom: 6px; }
.metric-value { font-family: 'IBM Plex Mono', monospace; font-size: 28px; font-weight: 500; color: #e6edf3; }
.metric-value.cyan { color: #21d4fd; }
.metric-sub { font-size: 11px; color: #7d8590; margin-top: 4px; }

/* 출처 뱃지 */
.badge {
    display: inline-block; padding: 2px 9px; border-radius: 5px;
    font-size: 11px; font-weight: 500; font-family: 'IBM Plex Mono', monospace;
    white-space: nowrap;
}
.badge-나라장터 { background:#1d4ed820; color:#60a5fa; border:1px solid #1d4ed840; }
.badge-국방부일반 { background:#15803d20; color:#4ade80; border:1px solid #15803d40; }
.badge-국방부공개 { background:#16653020; color:#34d399; border:1px solid #16653040; }
.badge-LH { background:#b4530920; color:#fb923c; border:1px solid #b4530940; }
.badge-가스공사 { background:#be185d20; color:#f472b6; border:1px solid #be185d40; }
.badge-수자원공사 { background:#4338ca20; color:#a78bfa; border:1px solid #4338ca40; }

/* 사이드바 */
.sidebar-section {
    background: #0d1117; border: 1px solid #30363d;
    border-radius: 8px; padding: 14px 16px; margin-bottom: 12px;
}
.sidebar-label { font-size: 11px; color: #7d8590; letter-spacing: 0.5px; margin-bottom: 8px; }

/* 테이블 */
[data-testid="stDataFrame"] { border: 1px solid #30363d; border-radius: 8px; }

/* 버튼 */
.stButton > button {
    background: #21d4fd !important; color: #0d1117 !important;
    font-weight: 600 !important; font-family: 'IBM Plex Mono', monospace !important;
    letter-spacing: 0.5px !important; border: none !important;
    border-radius: 7px !important;
}
.stButton > button:hover { background: #7ee8fa !important; }

/* 진행 표시 */
.stProgress > div > div > div { background: #21d4fd !important; }

/* 토글 */
[data-testid="stToggle"] label { color: #e6edf3 !important; }

/* input */
.stTextArea textarea, .stDateInput input {
    background: #0d1117 !important; color: #e6edf3 !important;
    border-color: #30363d !important;
}

/* 경고/정보 */
.stAlert { border-radius: 8px; }

/* 다운로드 버튼 */
[data-testid="stDownloadButton"] button {
    background: #161b22 !important; color: #21d4fd !important;
    border: 1px solid #21d4fd44 !important;
}
</style>
""", unsafe_allow_html=True)

# =====================================================================
# 0. 공통 설정
# =====================================================================
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS     = {'User-Agent': 'Mozilla/5.0'}
VERSION     = "v2.2"

DEFAULT_KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽",
                    "식물성", "부유물", "초본류", "초목류", "임목", "폐가구"]
OUR_LICENSES        = ['1226', '1227', '6786', '6770']
WASTE_LICENSE_NAMES = ['폐기물처리업', '폐기물수집운반업', '폐기물재활용업']

KWATER_DETAIL_BASE = ("https://ebid.kwater.or.kr/wq/index.do"
                       "?w2xPath=/ui/index.xml"
                       "&view=bidpblanc/bidpblancsttus/BIDBD32000002.xml&tndrPbanno=")
KOGAS_HOME = "https://k-ebid.kogas.or.kr"
D2B_HOME   = "https://www.d2b.go.kr/"
LH_HOME    = "https://ebid.lh.or.kr/"

# =====================================================================
# 1. 필터 함수
# =====================================================================
REGION_FREE = ['전국', '제한없음']

def _region_token_pass(token: str, test_mode=False) -> bool:
    if test_mode: return True
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

def lh_clean(text):
    return re.sub(r'<!\[CDATA\[|\]\]>','',text).strip() if text else ""

def lh_license_pass(item, test_mode=False) -> bool:
    if test_mode: return True
    for n in range(1,11):
        slots = [lh_clean(item.findtext(f'req{n}Reqlic{m}Nm')) for m in range(1,11)]
        slots = [s for s in slots if s]
        if not slots: continue
        if not any(name in s for s in slots for name in WASTE_LICENSE_NAMES):
            return False
    return True

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
        except: pass

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
        if region_val != "확인불가" and not region_pass(region_val, test_mode): return None
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
        if license_val not in ("확인불가","제한없음") and not license_code_pass(license_val, test_mode): return None
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
    """
    v2.0 핵심 수정: bidNm/othbcNtatNm 파라미터 제거 → 전체조회+로컬필터
    (키워드 서버필터 시 0건이면 D2B가 items="" 반환 → str.get() 에러)
    """
    results   = []
    start_day = start.strftime("%Y%m%d")
    end_day   = end.strftime("%Y%m%d")

    # 일반경쟁 ── 키워드 없이 전체 조회 → 로컬 키워드+마감일 필터
    url_bid = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
    url_det = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancDetail"
    try:
        res_b = requests.get(url_bid,
            params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'},
            headers=HEADERS, timeout=15)
        if res_b.status_code == 200:
            items = res_b.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])
            items = [items] if isinstance(items, dict) else (items or [])
            for it in items:
                bid_nm = it.get('bidNm', '')
                matched_kw = [kw for kw in keywords if kw in bid_nm]
                if not matched_kw: continue
                clos_dt = str(it.get('biddocPresentnClosDt','') or '').replace('.0','').strip()[:8]
                if clos_dt and not (start_day <= clos_dt <= end_day): continue
                p_det = {'serviceKey': SERVICE_KEY, '_type': 'json',
                         'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'),
                         'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'),
                         'dcsNo': it.get('dcsNo')}
                area, open_dt, budget, g2b_no, lcns = "제한없음", it.get('opengDt','-'), 0, None, "제한없음"
                det = {}
                try:
                    det = requests.get(url_det, params=p_det, headers=HEADERS, timeout=8) \
                              .json().get('response',{}).get('body',{}).get('item',{})
                    if isinstance(det, dict):
                        area    = det.get('areaLmttList') or "제한없음"
                        open_dt = det.get('opengDt') or open_dt
                        budget  = det.get('budgetAmount') or it.get('budgetAmount') or 0
                        g2b_no  = det.get('g2bPblancNo')
                        lcns    = det.get('lcnsLmttList') or "제한없음"
                except: pass
                if not region_pass(area, test_mode): continue
                if lcns not in ("","제한없음") and not license_code_pass(lcns, test_mode): continue
                results.append(to_row(
                    source='국방부(일반경쟁)', notice_no=g2b_no or it.get('pblancNo','-'),
                    title=bid_nm, agency=it.get('ornt','-'),
                    notice_dt=format_d2b_dt(it.get('pblancDate','-')),
                    close_dt=format_d2b_dt(it.get('biddocPresentnClosDt','-')),
                    open_dt=format_d2b_dt(open_dt),
                    amount=int(pd.to_numeric(budget, errors='coerce') or 0),
                    region=area, license_info=lcns, keyword=','.join(matched_kw), url=D2B_HOME,
                ))
    except: pass

    # 공개수의 ── 마감일 서버파라미터, 키워드 로컬 필터
    url_priv = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList"
    url_pdet = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanDetail"
    try:
        res_p = requests.get(url_priv,
            params={'serviceKey': SERVICE_KEY, '_type': 'json', 'numOfRows': '500',
                    'prqudoPresentnClosDateBegin': start_day,
                    'prqudoPresentnClosDateEnd':   end_day},
            headers=HEADERS, timeout=15)
        if res_p.status_code == 200:
            items = res_p.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])
            items = [items] if isinstance(items, dict) else (items or [])
            for it in items:
                bid_nm = it.get('othbcNtatNm', '')
                matched_kw = [kw for kw in keywords if kw in bid_nm]
                if not matched_kw: continue
                p_det = {'serviceKey': SERVICE_KEY, '_type': 'json',
                         'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'),
                         'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'),
                         'dcsNo': it.get('dcsNo'), 'iemNo': it.get('iemNo'),
                         'ntatPlanDate': it.get('ntatPlanDate')}
                area, open_dt, budget, g2b_no, lcns = "제한없음", it.get('opengDt','-'), 0, None, "제한없음"
                det = {}
                try:
                    det = requests.get(url_pdet, params=p_det, headers=HEADERS, timeout=8) \
                              .json().get('response',{}).get('body',{}).get('item',{})
                    if isinstance(det, dict):
                        area    = det.get('areaLmttList') or "제한없음"
                        open_dt = det.get('opengDt') or open_dt
                        budget  = det.get('budgetAmount') or it.get('budgetAmount') or 0
                        g2b_no  = det.get('g2bPblancNo')
                        lcns    = det.get('lcnsLmttList') or "제한없음"
                except: pass
                if not region_pass(area, test_mode): continue
                if lcns not in ("","제한없음") and not license_code_pass(lcns, test_mode): continue
                results.append(to_row(
                    source='국방부(공개수의)', notice_no=g2b_no or it.get('pblancNo','-'),
                    title=bid_nm, agency=it.get('ornt','-'),
                    notice_dt='-',
                    close_dt=format_d2b_dt(it.get('prqudoPresentnClosDt','-')),
                    open_dt=format_d2b_dt(open_dt),
                    amount=int(pd.to_numeric(budget, errors='coerce') or 0),
                    region=area, license_info=lcns, keyword=','.join(matched_kw), url=D2B_HOME,
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
        clean_xml = re.sub(r'<\?xml.*?>','',response.text)
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
        sd=start.strftime("%Y%m%d"); ed=end.strftime("%Y%m%d")
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
with st.sidebar:
    st.markdown(f"""
    <div style="padding:16px 0 12px;">
        <div style="font-family:'IBM Plex Mono',monospace;font-size:16px;color:#21d4fd;letter-spacing:2px;">📡 BID RADAR</div>
        <div style="font-size:11px;color:#7d8590;margin-top:2px;">{VERSION} · 폐기물 입찰 자동 탐지</div>
    </div>
    """, unsafe_allow_html=True)

    today = datetime.now()
    st.markdown('<div class="sidebar-label">📅 검색기간</div>', unsafe_allow_html=True)
    date_range = st.date_input("", value=(today-timedelta(days=6), today),
                                label_visibility="collapsed")
    start_dt, end_dt = (date_range if isinstance(date_range,tuple) and len(date_range)==2
                        else (today-timedelta(days=6), today))
    start_dt = datetime.combine(start_dt, datetime.min.time())
    end_dt   = datetime.combine(end_dt,   datetime.min.time())

    st.markdown('<div class="sidebar-label" style="margin-top:12px;">🎯 키워드</div>', unsafe_allow_html=True)
    kw_text  = st.text_area("", value=", ".join(DEFAULT_KEYWORDS), height=90,
                             label_visibility="collapsed")
    keywords = tuple(k.strip() for k in kw_text.split(",") if k.strip())

    st.markdown('<div class="sidebar-label" style="margin-top:12px;">🏛️ 출처기관</div>', unsafe_allow_html=True)
    sources  = st.multiselect("",
        ["나라장터","국방부(일반경쟁)","국방부(공개수의)","LH","가스공사","수자원공사"],
        default=["나라장터","국방부(일반경쟁)","국방부(공개수의)","LH","가스공사","수자원공사"],
        label_visibility="collapsed")

    test_mode = st.toggle("🧪 테스트 모드 (지역·면허 필터 OFF)", value=True)

    st.markdown(f"""
    <div style="margin-top:16px;padding:12px 14px;background:#0d1117;border:1px solid #30363d;border-radius:8px;">
        <div style="font-size:11px;color:#7d8590;line-height:1.8;">
            {'🔴 필터 OFF — 전체 공고 노출' if test_mode else '🟢 필터 ON — 조건 적용'}<br>
            📍 지역: 경기도·평택·화성·전국<br>
            🪪 면허: {', '.join(OUR_LICENSES)}<br>
            ⚠️ 가스공사·수자원공사 지역·면허 미지원
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    run = st.button("🔍  조회 실행", use_container_width=True)

# =====================================================================
# 4. 메인 화면
# =====================================================================
st.markdown(f"""
<div class="radar-header">
    <div class="radar-ver">{VERSION}</div>
    <div class="radar-title">🛰  폐기물 입찰 레이더</div>
    <div class="radar-sub">WASTE BID RADAR · {start_dt:%Y.%m.%d} – {end_dt:%Y.%m.%d} · 키워드 {len(keywords)}개 ·
    {'테스트 모드(필터 OFF)' if test_mode else '실운영 모드(필터 ON)'}</div>
</div>
""", unsafe_allow_html=True)

if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()
if "errors" not in st.session_state:
    st.session_state.errors = {}

if run:
    errors = {}
    results_map = {}

    # ★ 5개 기관 병렬 실행으로 속도 개선
    def run_agency(name, fn):
        try:
            return name, fn(), None
        except Exception as e:
            return name, [], str(e)

    steps = {
        "나라장터":        lambda: fetch_narajangter(keywords, start_dt, end_dt, test_mode),
        "국방부":          lambda: fetch_d2b(keywords, start_dt, end_dt, test_mode),
        "LH":             lambda: fetch_lh(keywords, start_dt, end_dt, test_mode),
        "가스공사":        lambda: fetch_kogas(keywords, start_dt, end_dt),
        "수자원공사":      lambda: fetch_kwater(keywords),
    }

    prog = st.progress(0, text="탐지 시작...")
    prog_cols = st.columns(5)
    status_texts = {n: c.empty() for n, c in zip(steps.keys(), prog_cols)}
    for n in steps: status_texts[n].markdown(f"<div style='font-size:11px;color:#7d8590;text-align:center'>{n}<br>⏳</div>", unsafe_allow_html=True)

    done_count = 0
    all_rows = []

    # 병렬로 5개 기관 동시 실행
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(run_agency, name, fn): name for name, fn in steps.items()}
        for future in as_completed(futures):
            name, rows, err = future.result()
            done_count += 1
            prog.progress(done_count / len(steps), text=f"{name} 완료 ({done_count}/{len(steps)})")
            if err:
                errors[name] = err
                status_texts[name].markdown(f"<div style='font-size:11px;color:#f85149;text-align:center'>{name}<br>❌ 오류</div>", unsafe_allow_html=True)
            else:
                all_rows.extend(rows)
                status_texts[name].markdown(f"<div style='font-size:11px;color:#3fb950;text-align:center'>{name}<br>✅ {len(rows)}건</div>", unsafe_allow_html=True)

    prog.progress(1.0, text="완료")

    df = pd.DataFrame(all_rows)
    if not df.empty:
        df = df[df['출처기관'].apply(
            lambda s: any(s.startswith(src.rstrip('(일반경쟁)').rstrip('(공개수의)')) or s == src
                         for src in sources)
        )]
    st.session_state.df = df
    st.session_state.errors = errors

df     = st.session_state.df
errors = st.session_state.get("errors", {})

# 오류 표시
if errors:
    for name, err in errors.items():
        st.warning(f"⚠️ {name} 조회 실패: {err}")

# 결과
if df.empty:
    st.markdown("""
    <div style="text-align:center;padding:80px 0;color:#7d8590;">
        <div style="font-size:40px;margin-bottom:16px;">📡</div>
        <div style="font-size:16px;font-family:'IBM Plex Mono',monospace;color:#30363d;">NO SIGNAL</div>
        <div style="font-size:13px;margin-top:8px;">좌측에서 조건을 설정하고 <b style="color:#21d4fd">조회 실행</b>을 누르세요.</div>
    </div>
    """, unsafe_allow_html=True)
else:
    # 메트릭 카드
    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-card highlight">
            <div class="metric-label">총 공고 수</div>
            <div class="metric-value cyan">{len(df)}</div>
            <div class="metric-sub">건</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">출처기관</div>
            <div class="metric-value">{df['출처기관'].nunique()}</div>
            <div class="metric-sub">개 기관</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">지역 확인불가</div>
            <div class="metric-value">{df['지역제한'].astype(str).str.contains('확인불가').sum()}</div>
            <div class="metric-sub">건 (가스·수자원)</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">면허 확인불가</div>
            <div class="metric-value">{df['면허정보'].astype(str).str.contains('확인불가').sum()}</div>
            <div class="metric-sub">건</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 기관별 분포 (간단한 텍스트 차트)
    counts = df['출처기관'].value_counts()
    badge_map = {
        '나라장터':'badge-나라장터', '국방부(일반경쟁)':'badge-국방부일반',
        '국방부(공개수의)':'badge-국방부공개', 'LH':'badge-LH',
        '가스공사':'badge-가스공사', '수자원공사':'badge-수자원공사'
    }
    badges = " ".join(
        f'<span class="badge {badge_map.get(k,"")}"> {k} &nbsp; {v}건 </span>'
        for k, v in counts.items()
    )
    st.markdown(f'<div style="margin-bottom:16px;display:flex;flex-wrap:wrap;gap:6px;">{badges}</div>',
                unsafe_allow_html=True)

    # 데이터 테이블
    st.dataframe(df, use_container_width=True, height=560,
        column_config={
            "공고명":   st.column_config.TextColumn("공고명", width="large"),
            "금액(원)": st.column_config.TextColumn("금액(원)"),
            "면허정보": st.column_config.TextColumn("면허정보", width="medium"),
            "상세URL":  st.column_config.LinkColumn("상세URL", display_text="열기"),
        })

    # 다운로드
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='통합결과', index=False)
        for src in df['출처기관'].unique():
            df[df['출처기관']==src].to_excel(writer, sheet_name=str(src)[:31], index=False)
    st.download_button(
        "📥  엑셀 다운로드",
        data=buf.getvalue(),
        file_name=f"입찰레이더_{datetime.now():%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
