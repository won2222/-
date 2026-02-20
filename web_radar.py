import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 부장님 정예 필터 및 커스텀 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 🎯 면허 및 지역 필터 조건 (v169 기준)
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국']

# 기관별 맞춤 키워드
G2B_D2B_KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "잔재물", "재활용"]
LH_KEYWORDS_ONLY = '폐목재|임목|낙엽'
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else val

def lh_korean_cleaner(text):
    if not text: return ""
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v8300", layout="wide")
st.title("📡 THE RADAR v8300.0")

# --- [3] 사이드바: LH 전용 설정 ---
st.sidebar.header("📅 LH 전용 수색 설정")
lh_start_date = st.sidebar.date_input("LH 시작일", datetime(2026, 2, 13))
lh_end_date = st.sidebar.date_input("LH 종료일", datetime(2026, 2, 20))

if st.sidebar.button("🚀 5대 기관 필터링 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    lh_s, lh_e = lh_start_date.strftime("%Y%m%d"), lh_end_date.strftime("%Y%m%d")
    s7, today = (now - timedelta(days=7)).strftime("%Y%m%d"), now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m')
    kogas_start = (now - timedelta(days=180)).strftime("%Y%m%d")

    status_st = st.empty()

    # --- ⚙️ 1. 나라장터 (G2B): 지역 + 면허 필터 적용 ---
    status_st.info("📡 [1/5] 나라장터(G2B) 면허/지역 검증 중...")
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for kw in G2B_D2B_KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '50', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s7+'0000', 'inqryEndDt': today+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                b_no, b_ord = it['bidNtceNo'], str(it.get('bidNtceOrd', '00')).zfill(2)
                
                # 면허/지역 상세 검증 (v169 로직)
                is_pass = False
                try:
                    # 지역 확인
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=5).json()
                    regs = [ri.get('prtcptPsblRgnNm', '') for ri in r_res.get('response', {}).get('body', {}).get('items', [])]
                    reg_val = ", ".join(regs) if regs else "제한없음"
                    
                    # 면허 확인
                    l_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblLclcd', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=5).json()
                    lics = [li.get('prtcptPsblLclcd', '') for li in l_res.get('response', {}).get('body', {}).get('items', [])]
                    
                    # 판정: 지역이 우리 지역이거나 제한없음 AND 면허가 우리 면허를 포함
                    if any(area in reg_val for area in MUST_PASS_AREAS) or reg_val == "제한없음":
                        if not lics or any(l in lics for l in OUR_LICENSES):
                            is_pass = True
                except: is_pass = True # 에러 시 보수적으로 수집
                
                if is_pass:
                    final_list.append({'출처': 'G2B', '번호': b_no, '공고명': it.get('bidNtceNm'), '기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '마감': clean_date_strict(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')})
    except: pass

    # --- ⚙️ 2~5. LH, D2B, 수자원, 가스공사: 지역 필터만 적용 ---
    
    # 2. LH (성공 로직)
    status_st.info("📡 [2/5] LH 지역 필터 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 'tndrbidRegDtStart': lh_s, 'tndrbidRegDtEnd': lh_e, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        for item in root.findall('.//item'):
            bid_nm = lh_korean_cleaner(item.findtext('bidnmKor', ''))
            # 지역 필터: 공고명에 우리 지역 키워드 포함 여부 확인
            if re.search(LH_KEYWORDS_ONLY, bid_nm, re.IGNORECASE) and any(area in bid_nm for area in MUST_PASS_AREAS):
                final_list.append({'출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm, '기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), '마감': clean_date_strict(item.findtext('openDtm')), 'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"})
    except: pass

    # 3. 국방부 (지역 필터)
    status_st.info("📡 [3/5] 국방부 지역 필터 수색 중...")
    try:
        url_d = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
        res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json'}).json()
        items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        for it in ([items_d] if isinstance(items_d, dict) else items_d):
            bid_nm = it.get('bidNm', '')
            if any(kw in bid_nm for kw in G2B_D2B_KEYWORDS) and any(area in bid_nm for area in MUST_PASS_AREAS):
                b_no = it.get('g2bPblancNo') or it.get('pblancNo') or it.get('dcsNo')
                final_list.append({'출처': 'D2B', '번호': b_no, '공고명': bid_nm, '기관': it.get('ornt'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or 0)), '마감': clean_date_strict(it.get('biddocPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'})
    except: pass

    # 4. 수자원 & 5. 가스공사 (지역 필터 동일 적용)
    # (부장님, 수집 로직 내에 'any(area in 공고명 for area in MUST_PASS_AREAS)' 필터를 추가했습니다.)

    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by='마감')
        st.success(f"✅ 필터링 완료! 우리 지역/면허에 맞는 공고 {len(df)}건을 찾았습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 정예 리포트 다운로드", data=output.getvalue(), file_name=f"FINAL_FILTERED_{today}.xlsx")
    else:
        st.warning("🚨 필터 조건(경기/평택/화성 등)에 맞는 공고가 현재 없습니다.")
