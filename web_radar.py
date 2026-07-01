# -*- coding: utf-8 -*-
"""
폐기물 입찰 레이더 (BID RADAR) ── v2.3 (2026-07-01)
v2.3  국방부 마감일 범위 수정 (과거7일→미래30일) / 가독성 UI 개선
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
    page_title="폐기물 입찰 레이더",
    page_icon="📡", layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}

/* ── 전체 배경 ── */
.stApp { background: #f5f6fa; }
[data-testid="stSidebar"] {
    background: #1e2235;
}
[data-testid="stSidebar"] * { color: #dde3f0 !important; }
[data-testid="stSidebar"] .stTextArea textarea {
    background: #252a3d !important; border-color: #374060 !important;
    color: #dde3f0 !important; font-size: 13px !important;
}
[data-testid="stSidebar"] [data-testid="stDateInput"] input {
    background: #252a3d !important; border-color: #374060 !important;
    color: #dde3f0 !important;
}

/* ── 헤더 ── */
.app-header {
    background: #1e2235;
    border-radius: 14px;
    padding: 26px 32px 22px;
    margin-bottom: 20px;
    display: flex; align-items: center; justify-content: space-between;
}
.app-header-left { }
.app-name {
    font-family: 'JetBrains Mono', monospace;
    font-size: 22px; font-weight: 500;
    color: #ffffff; letter-spacing: 1.5px; margin: 0;
}
.app-name span { color: #4f9eff; }
.app-meta { font-size: 12px; color: #8892aa; margin-top: 5px; letter-spacing: 0.3px; }
.app-badge {
    background: #252a3d; border: 1px solid #374060;
    border-radius: 8px; padding: 8px 16px; text-align: right;
}
.app-badge-ver { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #4f9eff; }
.app-badge-date { font-size: 12px; color: #8892aa; margin-top: 2px; }

/* ── 메트릭 카드 ── */
.metrics-row { display: flex; gap: 12px; margin-bottom: 18px; }
.metric-card {
    flex: 1; background: #ffffff;
    border: 1px solid #e2e6f0;
    border-radius: 10px; padding: 16px 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,.05);
}
.metric-card.primary { border-left: 3px solid #4f9eff; }
.metric-label { font-size: 11px; font-weight: 500; color: #8892aa;
    text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 6px; }
.metric-val { font-family: 'JetBrains Mono', monospace;
    font-size: 30px; font-weight: 500; color: #1e2235; line-height: 1; }
.metric-val.blue { color: #4f9eff; }
.metric-desc { font-size: 11px; color: #b0b8cc; margin-top: 4px; }

/* ── 소스 뱃지 ── */
.src-tag {
    display: inline-block; padding: 2px 9px; border-radius: 20px;
    font-size: 11px; font-weight: 600; letter-spacing: 0.2px;
    white-space: nowrap;
}
.tag-나라장터    { background:#eff6ff; color:#2563eb; border:1px solid #bfdbfe; }
.tag-국방부일반  { background:#f0fdf4; color:#15803d; border:1px solid #bbf7d0; }
.tag-국방부공개  { background:#ecfdf5; color:#065f46; border:1px solid #a7f3d0; }
.tag-LH         { background:#fff7ed; color:#c2410c; border:1px solid #fed7aa; }
.tag-가스공사    { background:#fdf4ff; color:#7e22ce; border:1px solid #e9d5ff; }
.tag-수자원공사  { background:#eff6ff; color:#0369a1; border:1px solid #bae6fd; }

/* ── 진행 상태 행 ── */
.progress-row {
    display: flex; gap: 8px; margin: 14px 0 8px;
    background: #ffffff; border: 1px solid #e2e6f0;
    border-radius: 10px; padding: 14px 20px;
}
.prog-item { flex: 1; text-align: center; }
.prog-name { font-size: 12px; color: #8892aa; margin-bottom: 4px; }
.prog-status { font-size: 14px; }

/* ── 빈 상태 ── */
.empty-state {
    text-align: center; padding: 80px 0;
    background: #ffffff; border: 1px solid #e2e6f0;
    border-radius: 12px;
}
.empty-icon { font-size: 48px; margin-bottom: 12px; }
.empty-title { font-family: 'JetBrains Mono', monospace; font-size: 16px; color: #b0b8cc; }
.empty-hint { font-size: 13px; color: #b0b8cc; margin-top: 8px; }

/* ── 버튼 ── */
.stButton > button {
    background: #4f9eff !important; color: #ffffff !important;
    border: none !important; border-radius: 8px !important;
    font-weight: 600 !important; font-size: 14px !important;
    padding: 10px !important;
}
.stButton > button:hover { background: #2563eb !important; }
[data-testid="stDownloadButton"] button {
    background: #f0fdf4 !important; color: #15803d !important;
    border: 1px solid #bbf7d0 !important; border-radius: 8px !important;
    font-weight: 500 !important;
}
.stProgress > div > div > div { background: #4f9eff !important; }
[data-testid="stDataFrame"] {
    background: #fff; border: 1px solid #e2e6f0;
    border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.05);
}
</style>
""", unsafe_allow_html=True)

# =====================================================================
# 공통 설정
# =====================================================================
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS     = {'User-Agent': 'Mozilla/5.0'}
VERSION     = "v2.5"
TODAY       = datetime.now()

DEFAULT_KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽",
                    "식물성", "부유물", "초본류", "초목류", "임목", "폐가구"]
OUR_LICENSES        = ['1226', '1227', '6786', '6770']
WASTE_LICENSE_NAMES = ['폐기물처리업', '폐기물수집운반업', '폐기물재활용업']
KWATER_DETAIL_BASE = "https://ebid.kwater.or.kr/wq/index.do?w2xPath=/ui/index.xml&view=bidpblanc/bidpblancsttus/BIDBD32000002.xml&tndrPbanno="
KOGAS_HOME = "https://k-ebid.kogas.or.kr"
D2B_HOME   = "https://www.d2b.go.kr/"
LH_HOME    = "https://ebid.lh.or.kr/"

def _region_token_pass(token):
    token = token.strip()
    if not token: return True
    if any(f in token for f in ['전국','제한없음']): return True
    if '평택' in token or '화성' in token: return True
    if token == '경기도': return True
    return False

def region_pass(region_text, test_mode=False):
    if test_mode: return True
    if region_text is None: return True
    tokens = list(region_text) if isinstance(region_text,(list,tuple,set)) \
             else re.split(r'[,]', str(region_text).strip())
    return any(_region_token_pass(t) for t in tokens) if tokens else True

def license_code_pass(license_text, test_mode=False):
    if test_mode: return True
    if not license_text: return True
    return any(code in str(license_text) for code in OUR_LICENSES)

def lh_clean(text):
    return re.sub(r'<!\[CDATA\[|\]\]>','',text).strip() if text else ""

def lh_license_pass(item, test_mode=False):
    if test_mode: return True
    for n in range(1,11):
        slots = [lh_clean(item.findtext(f'req{n}Reqlic{m}Nm')) for m in range(1,11)]
        slots = [s for s in slots if s]
        if not slots: continue
        if not any(name in s for s in slots for name in WASTE_LICENSE_NAMES): return False
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
# 기관별 수집
# =====================================================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_narajangter(keywords, start, end, test_mode):
    service_key = unquote(SERVICE_KEY)
    s_date = start.strftime("%Y%m%d0000"); e_date = end.strftime("%Y%m%d2359")
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
        b_no=row['bidNtceNo']; b_ord=str(row.get('bidNtceOrd','000')).zfill(3)
        bp={'ServiceKey':service_key,'type':'json','inqryDiv':'2','bidNtceNo':b_no,'bidNtceOrd':b_ord}
        region_val="확인불가"
        try:
            r_items=requests.get(url_base+'getBidPblancListInfoPrtcptPsblRgn',params=bp,timeout=8)\
                .json().get('response',{}).get('body',{}).get('items',[])
            regs=[str(ri.get('prtcptPsblRgnNm','')) for ri in ([r_items] if isinstance(r_items,dict) else r_items) if ri.get('prtcptPsblRgnNm')]
            region_val=", ".join(set(regs)) if regs else "제한없음"
        except: pass
        if region_val!="확인불가" and not region_pass(region_val,test_mode): return None
        license_val="확인불가"
        try:
            l_items=requests.get(url_base+'getBidPblancListInfoLicenseLimit',params=bp,timeout=8)\
                .json().get('response',{}).get('body',{}).get('items',[])
            lics=[]
            for li in ([l_items] if isinstance(l_items,dict) else l_items):
                v=li.get('lcnsLmtNm') or li.get('permsnIndstrytyList','')
                if v: lics.append(str(v))
            license_val=" / ".join(set(lics)) if lics else "제한없음"
        except: pass
        if license_val not in ("확인불가","제한없음") and not license_code_pass(license_val,test_mode): return None
        return to_row(source='나라장터',notice_no=b_no,title=row.get('bidNtceNm','-'),
            agency=row.get('dminsttNm','-'),notice_dt=row.get('bidNtceDate',row.get('rgstDt','-')),
            close_dt=row.get('bidClseDt','-'),open_dt=row.get('opengDt','-'),
            amount=row.get('asignBdgtAmt',row.get('bdgtAmt','-')),
            region=region_val,license_info=license_val,keyword=row.get('_keyword','-'),
            url=row.get('bidNtceDtlUrl','-'))

    results=[]
    with ThreadPoolExecutor(max_workers=20) as ex:
        for r in as_completed({ex.submit(fetch_detail,row):row for _,row in df_bids.reset_index(drop=True).iterrows()}):
            try:
                v=r.result()
                if v: results.append(v)
            except: pass
    return results


@st.cache_data(ttl=600, show_spinner=False)
def fetch_d2b(keywords, start, end, test_mode):
    """
    v2.6 - 원본(국방부_필터링_완성_최종.py) 로직 100% 그대로 반영
    핵심: p_det에 'service_key'(언더스코어), 날짜필터 없음, items or[] 없음
    """
    results  = []
    today_dt = TODAY
    d2b_start = (today_dt - timedelta(days=10)).strftime("%Y%m%d")
    d2b_end   = (today_dt + timedelta(days=20)).strftime("%Y%m%d")

    target_areas = ["경기도", "평택시", "화성시", "제한없음", "전국"]

    api_configs = [
        {
            'type': '일반입찰',
            'list_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList',
            'det_url':  'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancDetail',
            'source':   '국방부(일반경쟁)',
        },
        {
            'type': '공개수의',
            'list_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList',
            'det_url':  'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanDetail',
            'source':   '국방부(공개수의)',
        },
    ]

    for config in api_configs:
        # ★ 원본 그대로: 일반입찰은 날짜파라미터 없음, 공개수의만 날짜파라미터
        params = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
        if config['type'] == '공개수의':
            params.update({'prqudoPresentnClosDateBegin': d2b_start,
                           'prqudoPresentnClosDateEnd':   d2b_end})
        try:
            res = requests.get(config['list_url'], params=params, headers=HEADERS, timeout=15)
            if res.status_code != 200: continue

            # ★ 원본 그대로: or[] 없음
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

                # ★ 원본 그대로: 'service_key'(언더스코어)
                p_det = {
                    'service_key': SERVICE_KEY,
                    'pblancNo':    p_no,
                    'pblancOdr':   str(it.get('pblancOdr', '1')).split('.')[0],
                    'demandYear':  d_year,
                    'orntCode':    it.get('orntCode'),
                    'dcsNo':       d_no,
                    '_type':       'json',
                }
                if config['type'] == '공개수의':
                    p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})

                area, budget = "제한없음", 0
                try:
                    det_res  = requests.get(config['det_url'], params=p_det, headers=HEADERS, timeout=5).json()
                    det_data = det_res.get('response', {}).get('body', {}).get('item', {})
                    if isinstance(det_data, dict):
                        area         = det_data.get('areaLmttList') or "제한없음"
                        combined_g2b = det_data.get('g2bPblancNo') or combined_g2b
                        budget       = det_data.get('budgetAmount') or it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                except: pass

                # ★ 원본 그대로: progrsSttus + area 체크
                status = it.get('progrsSttus') or "진행중"
                if not ("진행중" in status or status == ""): continue
                if not any(t in area for t in target_areas): continue
                # 추가: 테스트모드 OFF일 때만 면허 필터
                lcns = ""
                if not test_mode and lcns not in ("", "제한없음") and not license_code_pass(lcns): continue

                close_dt_raw = it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')
                notice_dt_raw = it.get('pblancDate', '-')

                results.append(to_row(
                    source=config['source'],
                    notice_no=combined_g2b or p_no or '-',
                    title=bid_nm, agency=it.get('ornt', '-'),
                    notice_dt=format_d2b_dt(notice_dt_raw),
                    close_dt=format_d2b_dt(close_dt_raw),
                    open_dt=format_d2b_dt(it.get('opengDt', '-')),
                    amount=int(pd.to_numeric(budget, errors='coerce') or 0),
                    region=area, license_info='미조회',
                    keyword=','.join(matched_kw), url=D2B_HOME,
                ))
        except Exception: pass

    seen, dedup = set(), []
    for r in results:
        key = (r['출처기관'], r['공고번호'])
        if key not in seen: seen.add(key); dedup.append(r)
        else:
            for d in dedup:
                if (d['출처기관'],d['공고번호'])==key and r['매칭키워드'] not in d['매칭키워드']:
                    d['매칭키워드'] += f",{r['매칭키워드']}"
    return dedup


