import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import re
import io
from datetime import datetime, timedelta

# --- [1] 부장님 v90.0 LH 전용 클리너 (CDATA 제거) ---
def lh_korean_cleaner(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>', '', text)
    return text.strip()

# --- [2] 날짜 정규화 함수 (정렬 에러 방지용) ---
def normalize_date(val):
    if not val or val == "-": return "9999-12-31" # 날짜 없는 건 맨 뒤로
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s

# --- [3] 설정값 (부장님 원본 100% 준수) ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}
LH_KEYWORDS = '폐목재|임목|목재|나무|벌채|뿌리|폐기물|운반|재활용'
D2B_KEYWORDS = ["폐기물", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성"]

st.set_page_config(page_title="THE RADAR v5800", layout="wide")
st.title("📡 THE RADAR v5800.0")
st.info("🚀 LH 시설공사(Gb:1) 단독 타격 + 정렬 오류 수정 완료")

if st.sidebar.button("🚀 LH(v90) & 국방부 정밀 수색", type="primary"):
    final_list = []
    now = datetime.now()
    
    # 날짜 설정 (v90 방식)
    lh_start, lh_end = '20260201', '20260228'
    
    status_st = st.empty()

    # --- 1. LH (e-Bid) : 시설공사(Gb:1) 언어 ---
    status_st.info("📡 [LH포털] 시설공사 카테고리 침투 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        params_lh = {
            'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500',
            'tndrbidRegDtStart': lh_start, 'tndrbidRegDtEnd': lh_end,
            'cstrtnJobGb': '1' 
        }
        res_lh = requests.get(url_lh, params=params_lh, timeout=20)
        res_lh.encoding = res_lh.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        
        if "<resultCode>00</resultCode>" in clean_xml:
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                clean_nm = lh_korean_cleaner(item.findtext('bidnmKor', ''))
                if re.search(LH_KEYWORDS, clean_nm, re.IGNORECASE):
                    final_list.append({
                        '출처': 'LH(시설)',
                        '번호': item.findtext('bidNum'),
                        '공고명': clean_nm,
                        '기관': 'LH공사',
                        '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                        '마감': normalize_date(item.findtext('openDtm')), # 날짜 통일
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
    except: pass

    # --- 2. 국방부 (D2B) : v161/169 엔진 ---
    status_st.info("📡 [국방부] 데이터 수집 중...")
    try:
        url_d = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
        res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json'}, timeout=15).json()
        items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        for it in ([items_d] if isinstance(items_d, dict) else items_d):
            bid_nm = it.get('bidNm', '')
            if any(kw in bid_nm for kw in D2B_KEYWORDS):
                final_list.append({
                    '출처': 'D2B', '번호': it.get('pblancNo') or it.get('dcsNo'),
                    '공고명': bid_nm, '기관': it.get('ornt'),
                    '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or it.get('budgetAmount') or 0)),
                    '마감': normalize_date(it.get('biddocPresentnClosDt')), # 날짜 통일
                    'URL': 'https://www.d2b.go.kr'
                })
    except: pass

    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호'])
        # 🎯 정렬 에러 방지: 모든 날짜를 문자열로 강제 변환 후 정렬
        df['마감'] = df['마감'].astype(str)
        df = df.sort_values(by='마감')
        
        st.success(f"✅ 작전 성공! LH 시설공사 포함 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("⚠️ 현재 조건에 맞는 LH(시설) 및 국방부 공고가 없습니다.")
