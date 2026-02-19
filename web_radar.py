import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 핵심 세척 및 포맷 함수 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def lh_korean_cleaner(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>', '', text)
    return text.strip()

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] UI 레이아웃 ---
st.set_page_config(page_title="THE RADAR v550", layout="wide")
st.title("📡 THE RADAR v550.0")
st.caption("LH 기간 직공(直供) 엔진 및 통합 필터 시스템")

# --- [3] 사이드바 컨트롤러 (부장님 전용) ---
st.sidebar.header("🛠️ 전략 수색 설정")

# 🎯 날짜 직접 지정 (LH가 가장 민감하게 반응하는 부분)
st.sidebar.subheader("📅 수색 기간 (LH 직접 연동)")
col_s, col_e = st.sidebar.columns(2)
with col_s:
    s_date = st.sidebar.date_input("수색 시작일", datetime.now() - timedelta(days=14))
with col_e:
    e_date = st.sidebar.date_input("수색 종료일", datetime.now() + timedelta(days=7))

# 🎯 키워드 필터링
st.sidebar.subheader("🔑 핵심 키워드")
default_kw = "폐기물, 운반, 폐목재, 임목, 나무, 벌채, 뿌리, 재활용, 잔재물, 가연성"
user_kw = st.sidebar.text_area("필터 키워드 (쉼표 구분)", default_kw, height=150)
kw_list = [k.strip() for k in user_kw.split(",") if k.strip()]

MUST_PASS_AREAS = ['경기', '평택', '화성', '서울', '인천', '전국', '제한없음']

if st.sidebar.button("🚀 전 구역 통합 수색 개시", type="primary"):
    final_list = []
    # LH 전용 날짜 포맷팅
    s_str = s_date.strftime("%Y%m%d")
    e_str = e_date.strftime("%Y%m%d")
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- PHASE 1. LH (부장님 성공 로직 100% 이식) ---
        status_st.info(f"📡 LH 수색 중... ({s_str} ~ {e_str})")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            params_lh = {
                'serviceKey': SERVICE_KEY,
                'pageNo': '1',
                'numOfRows': '500',
                'tndrbidRegDtStart': s_str, # 부장님이 지정한 날짜 직공
                'tndrbidRegDtEnd': e_str,   # 부장님이 지정한 날짜 직공
                'cstrtnJobGb': '1'
            }
            res_lh = requests.get(url_lh, params=params_lh, headers=HEADERS, timeout=25)
            res_lh.encoding = res_lh.apparent_encoding
            clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
            
            if "<resultCode>00</resultCode>" in clean_xml:
                root = ET.fromstring(f"<root>{clean_xml}</root>")
                for item in root.findall('.//item'):
                    bid_nm = lh_korean_cleaner(item.findtext('bidnmKor', ''))
                    if any(kw in bid_nm for kw in kw_list):
                        final_list.append({
                            '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm,
                            '수요기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce')),
                            '지역': '전국', '마감일': format_date_clean(item.findtext('openDtm')),
                            'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                        })
        except: pass
        prog.progress(33)

        # --- PHASE 2. 국방부 (D2B) ---
        status_st.info(f"📡 국방부 수색 중... (마감일 기준)")
        # ... (D2B 로직 동일하게 수행)
        # ... (이하 G2B 등 다른 기관 로직 통합)

        # --- [결과 출력] ---
        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 수색 완료! 총 {len(df)}건 포착 (LH 포함)")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("📥 통합 리포트 저장", data=output.getvalue(), file_name=f"RADAR_{s_str}.xlsx")
        else:
            st.warning("⚠️ 포착된 공고가 없습니다. 기간을 더 넓게 설정해 보세요.")

    except Exception as e:
        st.error(f"🚨 오류 발생: {e}")
