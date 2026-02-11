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

# --- [1] 부장님 정예 커스텀 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
# 헤더를 실제 브라우저처럼 보강
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/xml, text/xml, */*'
}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

KWATER_DETAIL_BASE = "https://ebid.kwater.or.kr/wq/index.do?w2xPath=/ui/index.xml&view=/bidpblanc/bidpblancsttus/BIDBD32000002.xml&tndrPbanno="
KOGAS_DIRECT_URL = "https://bid.kogas.or.kr:9443/supplier/index.jsp"

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR", layout="wide")
st.title("📡 THE RADAR")
st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE SYSTEM")
st.divider()

if st.sidebar.button("🔍 전략 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    s_date = (now - timedelta(days=4)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m') 
    last_month = (now - timedelta(days=28)).strftime('%Y%m') 
    kogas_start = (now - timedelta(days=14)).strftime("%Y%m%d") 
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 (생략) ---
        # --- 2. LH (긴급 복구 로직) ---
        status_st.info("📡 [PHASE 2] LH 서버 접속 시도 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            params_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}
            
            res_lh = requests.get(url_lh, params=params_lh, headers=HEADERS, timeout=20)
            
            if res_lh.status_code == 200:
                # 인코딩 강제 설정 (깨짐 방지)
                res_lh.encoding = 'utf-8' if 'utf-8' in res_lh.text.lower() else res_lh.apparent_encoding
                
                # XML 데이터 정제
                xml_data = res_lh.text.strip()
                if "<item>" in xml_data:
                    clean_xml = re.sub(r'<\?xml.*\?>', '', xml_data).strip()
                    root = ET.fromstring(f"<root>{clean_xml}</root>")
                    
                    for item in root.findall('.//item'):
                        raw_nm = item.findtext('bidnmKor', '')
                        bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', raw_nm).strip()
                        if any(kw in bid_nm for kw in KEYWORDS):
                            b_no = item.findtext('bidNum')
                            final_list.append({
                                '출처':'LH', '번호':b_no, '공고명':bid_nm, '수요기관':'LH', 
                                '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), 
                                '지역':'전국', '마감일':format_date_clean(item.findtext('openDtm')), 
                                'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"
                            })
                else:
                    st.sidebar.warning("⚠️ LH 신규 공고 없음")
            else:
                st.sidebar.error(f"❌ LH 서버 응답 에러 ({res_lh.status_code})")
        except Exception as e:
            st.sidebar.error(f"❌ LH 서버 연결 지연")

        # --- 3~5사 로직 동일 (중략) ---
        # ... (이전 코드의 G2B, D2B, K-water, KOGAS 로직 유지) ...

        # --- [최종 결과 출력] ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            counts = df['출처'].value_counts()
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("G2B", f"{counts.get('G2B', 0)}건")
            c2.metric("LH", f"{counts.get('LH', 0)}건")
            c3.metric("D2B", f"{counts.get('D2B(일반)',0)+counts.get('D2B(수의)',0)}건")
            c4.metric("K-water", f"{counts.get('K-water', 0)}건")
            c5.metric("KOGAS", f"{counts.get('KOGAS', 0)}건")
            
            st.write("")
            st.success(f"✅ 총 {len(df)}건 확보.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            # 엑셀 다운로드 (부장님 서식)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='RADAR_REPORT')
                workbook, worksheet = writer.book, writer.sheets['RADAR_REPORT']
                h_fmt = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#1E3A8A', 'border': 1, 'align': 'center'})
                for c_idx, val in enumerate(df.columns.values): worksheet.write(0, c_idx, val, h_fmt)
            st.download_button(label="📥 전략 리포트(Excel) 다운로드", data=output.getvalue(), file_name=f"RADAR_{today_str}.xlsx")
        else:
            st.warning("⚠️ 현재 조건에 부합하는 공고가 없습니다.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
