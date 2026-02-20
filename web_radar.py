import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 부장님 정예 커스텀 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 🎯 면허 및 지역 필터 조건 (v169 기반)
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

# 기관별 키워드
KEYWORDS_GEN = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "잔재물", "재활용"]
LH_KEYWORDS_REGEX = '폐목재|임목|낙엽'
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else val

def lh_cleaner(text):
    if not text: return ""
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v7800", layout="wide")
st.title("📡 THE RADAR v7800.0")

# --- [3] 사이드바: LH 전용 설정 ---
st.sidebar.header("📅 LH 전용 수색 설정")
lh_start = st.sidebar.date_input("LH 시작일", datetime(2026, 2, 13))
lh_end = st.sidebar.date_input("LH 종료일", datetime(2026, 2, 20))

if st.sidebar.button("🚀 5대 기관 통합 필터링 수색 개시", type="primary"):
    all_basket = [] # 모든 공고를 담을 통합 바구니
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    ls, le = lh_start.strftime("%Y%m%d"), lh_end.strftime("%Y%m%d")
    s7, today = (now - timedelta(days=7)).strftime("%Y%m%d"), now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m')
    kogas_start = (now - timedelta(days=180)).strftime("%Y%m%d")

    status_st = st.empty()

    # --- ⚙️ 1단계: 데이터 수집 (Data Collection) ---
    
    # 1-1. LH (XML / Gb:1)
    status_st.info("📡 [1/5] LH 시설공사 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': ls, 'tndrbidRegDtEnd': le, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        res_lh.encoding = 'utf-8'
        root = ET.fromstring(f"<root>{re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()}</root>")
        for item in root.findall('.//item'):
            bid_nm = lh_cleaner(item.findtext('bidnmKor', ''))
            if re.search(LH_KEYWORDS_REGEX, bid_nm, re.IGNORECASE):
                all_basket.append({'출처':'LH', '번호':item.findtext('bidNum'), '공고명':bid_nm, '기관':'LH공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), '마감':clean_date_strict(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"})
    except: pass

    # 1-2. 국방부 (D2B / 통합공고번호)
    status_st.info("📡 [2/5] 국방부 정밀 수색 중...")
    try:
        url_d = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
        res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json'}, timeout=15).json()
        items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        for it in ([items_d] if isinstance(items_d, dict) else items_d):
            bid_nm = it.get('bidNm', '')
            if any(kw in bid_nm for kw in KEYWORDS_GEN):
                b_no = it.get('g2bPblancNo') or it.get('pblancNo') or it.get('dcsNo')
                all_basket.append({'출처':'D2B', '번호':b_no, '공고명':bid_nm, '기관':it.get('ornt'), '예산':int(pd.to_numeric(it.get('asignBdgtAmt') or 0)), '마감':clean_date_strict(it.get('biddocPresentnClosDt')), 'URL':'https://www.d2b.go.kr'})
    except: pass

    # 1-3. 나라장터 (G2B)
    status_st.info("📡 [3/5] 나라장터 수색 중...")
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in KEYWORDS_GEN:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '50', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s7+'0000', 'inqryEndDt': today+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b, params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                all_basket.append({'출처':'G2B', '번호':it.get('bidNtceNo'), '공고명':it.get('bidNtceNm'), '기관':it.get('dminsttNm'), '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '마감':clean_date_strict(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
    except: pass

    # 1-4. 수자원공사 (K-water)
    status_st.info("📡 [4/5] 수자원공사 수색 중...")
    for kw in KWATER_KEYWORDS:
        try:
            res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", params={'serviceKey': SERVICE_KEY, 'searchDt': search_month, 'bidNm': kw, '_type': 'json'}, timeout=10).json()
            items_k = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for kit in ([items_k] if isinstance(items_k, dict) else items_k):
                all_basket.append({'출처':'K-water', '번호':kit.get('tndrPbanno'), '공고명':kit.get('tndrPblancNm'), '기관':'수자원공사', '예산':0, '마감':clean_date_strict(kit.get('tndrPblancEnddt')), 'URL':'https://ebid.kwater.or.kr'})
        except: continue

    # 1-5. 가스공사 (KOGAS)
    status_st.info("📡 [5/5] 가스공사 수색 중...")
    try:
        res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '200', 'DOCDATE_START': kogas_start}, timeout=15)
        root_kg = ET.fromstring(res_kg.text)
        for it in root_kg.findall('.//item'):
            nm = it.findtext('NOTICE_NAME') or ''
            if any(kw in nm for kw in KOGAS_KEYWORDS):
                all_basket.append({'출처':'KOGAS', '번호':it.findtext('NOTICE_CODE'), '공고명':nm, '기관':'가스공사', '예산':0, '마감':clean_date_strict(it.findtext('END_DT')), 'URL':'https://k-ebid.kogas.or.kr'})
    except: pass

    # --- ⚙️ 2단계: 필터링 및 출력 (Filtering) ---
    status_st.empty()
    if all_basket:
        df = pd.DataFrame(all_basket).drop_duplicates(subset=['번호'])
        
        # 선호 지역 가점 부여 정렬
        def get_priority(row):
            if any(area in row['공고명'] for area in MUST_PASS_AREAS): return 0
            return 1

        df['우선순위'] = df.apply(get_priority, axis=1)
        df = df.sort_values(by=['우선순위', '마감'])
        
        st.success(f"✅ 수색 완료! 총 {len(df)}건의 공고를 확보했습니다.")
        st.dataframe(df.drop(columns=['우선순위']).style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 통합 필터링 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_V7800_{today}.xlsx")
    else:
        st.warning("⚠️ 모든 기관을 수색했으나 조건에 맞는 공고가 없습니다.")
