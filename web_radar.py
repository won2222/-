import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import time
import pytz

# --- [1] 부장님 정예 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음', '부산', '경남'] # 부산/경남 추가

KWATER_DETAIL_BASE = "https://ebid.kwater.or.kr/wq/index.do?w2xPath=/ui/index.xml&view=/bidpblanc/bidpblancsttus/BIDBD32000002.xml&tndrPbanno="
KOGAS_DIRECT_URL = "https://bid.kogas.or.kr:9443/supplier/index.jsp"

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 레이아웃 ---
st.set_page_config(page_title="THE RADAR", layout="wide")
st.title("📡 THE RADAR")
st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE SYSTEM")
st.divider()

if st.sidebar.button("🔍 전략 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 🎯 수색 기간: 캡처하신 2/10일 공고 포착을 위해 넉넉하게 7일
    s_date = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m') 
    last_month = (now - timedelta(days=28)).strftime('%Y%m')
    kogas_start = (now - timedelta(days=14)).strftime("%Y%m%d")
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 ---
        status_st.info("📡 [PHASE 1] G2B 수색 중...")
        # ... (중략: 기존 G2B 로직) ...

        # --- 2. LH (공사 1 + 용역 5 통합 수색) ---
        status_st.info("📡 [PHASE 2] LH 공사 및 용역 통합 수색 중...")
        for job_gb in ['1', '5']:
            try:
                url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
                p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': job_gb}
                res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=15)
                res_lh.encoding = res_lh.apparent_encoding
                clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
                root = ET.fromstring(f"<root>{clean_xml}</root>")
                for item in root.findall('.//item'):
                    bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                    if any(kw in bid_nm for kw in KEYWORDS):
                        b_no = item.findtext('bidNum')
                        final_list.append({
                            '출처': f"LH({'공사' if job_gb=='1' else '용역'})", 
                            '번호': b_no, '공고명': bid_nm, '수요기관': 'LH', 
                            '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), 
                            '지역': '전국', '마감일': format_date_clean(item.findtext('openDtm')), 
                            'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"
                        })
            except: pass

        # --- 3~5사 로직 (중략: 기존 로직) ---
        # ...

        # --- 최종 출력 ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.metric("오늘의 전략 공고", f"{len(df)}건")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            # ... (중략: 엑셀 다운로드)
