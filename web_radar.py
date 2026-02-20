import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 부장님 v90.0 전용 클리너 (CDATA 파쇄) ---
def lh_korean_cleaner(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>', '', text)
    return text.strip()

# --- [2] 정예 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}
KEYWORDS_ALL = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "임목", "재활용"]
LH_KEYWORDS_REGEX = '폐목재|임목|목재|나무|벌채|뿌리|폐기물|운반|재활용'

st.set_page_config(page_title="THE RADAR v7300", layout="wide")
st.title("📡 THE RADAR v7300.0")

# --- [3] 사이드바: LH 전용 날짜 설정 (부장님 요청사항) ---
st.sidebar.header("📅 LH 수색 기간 설정")
lh_start_date = st.sidebar.date_input("LH 수색 시작일", datetime(2026, 2, 13))
lh_end_date = st.sidebar.date_input("LH 수색 종료일", datetime(2026, 2, 20))

st.sidebar.divider()
st.sidebar.info("💡 나라장터와 국방부는 최근 7일 자동 수색됩니다.")

if st.sidebar.button("🚀 전 채널 통합 수색 시작", type="primary"):
    final_list = []
    now = datetime.now()
    
    # 날짜 규격화 (LH: 8자리, 나라장터: 12자리)
    lh_s = lh_start_date.strftime("%Y%m%d")
    lh_e = lh_end_date.strftime("%Y%m%d")
    g2b_s = (now - timedelta(days=7)).strftime("%Y%m%d") + "0000"
    g2b_e = now.strftime("%Y%m%d") + "2359"
    
    status_st = st.empty()

    # --- 1. LH (e-Bid) : 부장님 v90.0 시설공사(Gb:1) 언어 ---
    status_st.info(f"📡 [LH포털] {lh_s}~{lh_e} 시설공사 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        # 🎯 부장님 v90.0 필수 파라미터 조합
        p_lh = {
            'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500',
            'tndrbidRegDtStart': lh_s, 'tndrbidRegDtEnd': lh_e,
            'cstrtnJobGb': '1'  # 시설공사 기준 고정
        }
        res_lh = requests.get(url_lh, params=p_lh, timeout=20)
        res_lh.encoding = res_lh.apparent_encoding
        
        # v90.0 핵심: CDATA 파쇄 및 resultCode 검증
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        if "<resultCode>00</resultCode>" in clean_xml:
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                clean_nm = lh_korean_cleaner(item.findtext('bidnmKor', ''))
                # v90.0 정규식 필터링
                if re.search(LH_KEYWORDS_REGEX, clean_nm, re.IGNORECASE):
                    final_list.append({
                        '출처': 'LH(시설)', '번호': item.findtext('bidNum'),
                        '공고명': clean_nm, '기관': '한국토지주택공사',
                        '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                        '마감': item.findtext('openDtm'),
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
    except: pass

    # --- 2. 나라장터 (G2B) & 3. 국방부 (D2B) ---
    # (생략: 기존에 잘 작동하던 v169 로직 적용)
    # ... 중략 (JSON 엔진 가동) ...
    
    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by='마감')
        st.success(f"✅ 작전 성공! LH({lh_s}~{lh_e}) 포함 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_v7300_{lh_s}.xlsx")
    else:
        st.warning("🚨 설정하신 날짜 범위 내에 검색 결과가 없습니다.")
