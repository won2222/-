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

# 기관별 맞춤 키워드
G2B_D2B_KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
LH_KEYWORDS_ONLY = '폐목재|임목|낙엽'
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국']

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

def lh_korean_cleaner(text):
    if not text: return ""
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

# --- [추가] 상세 정보 추출 함수 ---
def get_g2b_details(bid_no, bid_ord):
    """나라장터 지역 및 면허(업종) 정보 추출"""
    base_url = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
    region = "상세참조"
    license = "상세참조"
    
    try:
        # 지역 정보 호출
        r_res = requests.get(f"{base_url}/getBidPblancListInfoPrtcptPsblRgn", 
                             params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': bid_no, 'bidNtceOrd': bid_ord}, timeout=5).json()
        regions = [ri.get('prtcptPsblRgnNm', '') for ri in r_res.get('response', {}).get('body', {}).get('items', [])]
        if regions: region = ", ".join(list(set(regions)))
        
        # 면허(업종) 정보 호출
        l_res = requests.get(f"{base_url}/getBidPblancListInfoPrtcptPsblInstl", 
                             params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': bid_no, 'bidNtceOrd': bid_ord}, timeout=5).json()
        licenses = [li.get('instlNm', '') for li in l_res.get('response', {}).get('body', {}).get('items', [])]
        if licenses: license = ", ".join(list(set(licenses)))
    except: pass
    return region, license

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v8300", layout="wide")
st.title("📡 THE RADAR v8300.0")

# --- [3] 사이드바 ---
st.sidebar.header("📅 LH 전용 수색 설정")
lh_start_date = st.sidebar.date_input("LH 시작일", datetime(2026, 2, 13))
lh_end_date = st.sidebar.date_input("LH 종료일", datetime(2026, 2, 20))
st.sidebar.divider()

if st.sidebar.button("🚀 5대 기관 통합 정밀 수색", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    lh_s = lh_start_date.strftime("%Y%m%d")
    lh_e = lh_end_date.strftime("%Y%m%d")
    s7 = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_api = now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m')
    kogas_start = (now - timedelta(days=180)).strftime("%Y%m%d")

    status_st = st.empty()

    # --- 1. LH (e-Bid) ---
    status_st.info("📡 [1/5] LH 시설공사 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        res_lh = requests.get(url_lh, params={'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 'tndrbidRegDtStart': lh_s, 'tndrbidRegDtEnd': lh_e, 'cstrtnJobGb': '1'}, timeout=15)
        res_lh.encoding = res_lh.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        if "<resultCode>00</resultCode>" in clean_xml:
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                bid_nm = lh_korean_cleaner(item.findtext('bidnmKor', ''))
                if re.search(LH_KEYWORDS_ONLY, bid_nm, re.IGNORECASE):
                    final_list.append({
                        '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm, '기관': '한국토지주택공사', 
                        '지역': '전국(공고참조)', '면허': '상세참조',
                        '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), '마감': clean_date_strict(item.findtext('openDtm')),
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
    except: pass

    # --- 2. 국방부 (D2B) ---
    status_st.info("📡 [2/5] 국방부 수색 중...")
    try:
        url_d = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
        res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, headers=HEADERS).json()
        items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        for it in ([items_d] if isinstance(items_d, dict) else items_d):
            bid_nm = it.get('bidNm', '')
            if any(kw in bid_nm for kw in G2B_D2B_KEYWORDS):
                final_list.append({
                    '출처': 'D2B', '번호': it.get('g2bPblancNo') or it.get('pblancNo'), '공고명': bid_nm, '기관': it.get('ornt'), 
                    '지역': '국방부공고참조', '면허': '상세참조',
                    '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or 0)), '마감': clean_date_strict(it.get('biddocPresentnClosDt')), 
                    'URL': 'https://www.d2b.go.kr'
                })
    except: pass

    # --- 3. 나라장터 (G2B) ---
    status_st.info("📡 [3/5] 나라장터 상세 정보(지역/면허) 수집 중...")
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in G2B_D2B_KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '50', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s7+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b, params=p, timeout=10).json()
            items_g = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items_g] if isinstance(items_g, dict) else items_g):
                b_no = it.get('bidNtceNo')
                b_ord = it.get('bidNtceOrd')
                region, license = get_g2b_details(b_no, b_ord) # 상세 호출
                final_list.append({
                    '출처': 'G2B', '번호': b_no, '공고명': it.get('bidNtceNm'), '기관': it.get('dminsttNm'), 
                    '지역': region, '면허': license,
                    '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '마감': clean_date_strict(it.get('bidClseDt')), 
                    'URL': it.get('bidNtceDtlUrl')
                })
    except: pass

    # --- 4. 수자원공사 (K-water) ---
    status_st.info("📡 [4/5] 수자원공사 수색 중...")
    for kw in KWATER_KEYWORDS:
        try:
            url_k = "http://apis.data.go.kr/B500001/ebid/tndr3/servcList"
            p_k = {'serviceKey': SERVICE_KEY, 'searchDt': search_month, 'bidNm': kw, '_type': 'json'}
            res_k = requests.get(url_k, params=p_k, timeout=10).json()
            items_k = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for kit in ([items_k] if isinstance(items_k, dict) else items_k):
                final_list.append({
                    '출처': 'K-water', '번호': kit.get('tndrPbanno'), '공고명': kit.get('tndrPblancNm'), '기관': kit.get('cntrctDeptNm', '수자원공사'), 
                    '지역': '공고참조', '면허': '상세참조',
                    '예산': 0, '마감': clean_date_strict(kit.get('tndrPblancEnddt')), 'URL': 'https://ebid.kwater.or.kr'
                })
        except: continue

    # --- 5. 가스공사 (KOGAS) ---
    status_st.info("📡 [5/5] 가스공사 수색 중...")
    try:
        url_kg = "http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList"
        res_kg = requests.get(url_kg, params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': kogas_start}, timeout=15)
        root_kg = ET.fromstring(res_kg.text)
        for it in root_kg.findall('.//item'):
            title = it.findtext('NOTICE_NAME') or ''
            if any(kw in title for kw in KOGAS_KEYWORDS):
                final_list.append({
                    '출처': 'KOGAS', '번호': it.findtext('NOTICE_CODE'), '공고명': title, '기관': '한국가스공사', 
                    '지역': '공고참조', '면허': '상세참조',
                    '예산': 0, '마감': clean_date_strict(it.findtext('END_DT')), 'URL': 'https://k-ebid.kogas.or.kr'
                })
    except: pass

    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호'])
        df['마감'] = df['마감'].astype(str)
        df = df.sort_values(by=['마감'])
        
        # 컬럼 순서 조정
        cols = ['출처', '번호', '공고명', '기관', '지역', '면허', '예산', '마감', 'URL']
        df = df[cols]
        
        st.success(f"✅ 작전 완료! 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_V8300_{today_api}.xlsx")
    else:
        st.warning("⚠️ 현재 조건에 맞는 공고가 없습니다.")
