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
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음', '부산', '경남']

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
st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE (D2B RESTORED)")
st.divider()

if 'clicked' not in st.session_state:
    st.session_state.clicked = False

def click_button():
    st.session_state.clicked = True

st.sidebar.button("🔍 전략 수색 개시", type="primary", on_click=click_button)

if st.session_state.clicked:
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    s_date = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=7)).strftime("%Y%m%d") # 마감 임박용
    kogas_start = (now - timedelta(days=14)).strftime("%Y%m%d")
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 (생략/유지) ---
        status_st.info("📡 [PHASE 1] G2B 수색 중...")
        # (이전 코드의 G2B 고속 모드 로직 유지)

        # --- 2. LH (생략/유지) ---
        status_st.info("📡 [PHASE 2] LH 수색 중...")
        # (이전 코드의 LH 로직 유지)

        # --- 3. 국방부 (D2B) 복구 로직 ---
        status_st.info("📡 [PHASE 3] D2B 수색 중 (일반/수의 통합)...")
        d2b_configs = [
            {'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'c': 'biddocPresentnClosDt'},
            {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'c': 'prqudoPresentnClosDt'}
        ]
        for cfg in d2b_configs:
            try:
                p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '200', '_type': 'json'}
                if cfg['t'] == '수의':
                    p_d.update({'prqudoPresentnClosDateBegin': s_date, 'prqudoPresentnClosDateEnd': target_end_day})
                
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, headers=HEADERS, timeout=10).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in KEYWORDS):
                        final_list.append({
                            '출처': f"D2B({cfg['t']})",
                            '번호': it.get('pblancNo') or it.get('dcsNo', '-'),
                            '공고명': bid_nm,
                            '수요기관': it.get('ornt', '국방부'),
                            '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or it.get('budgetAmount') or 0, errors='coerce') or 0),
                            '지역': '국방부상세',
                            '마감일': format_date_clean(it.get(cfg['c'])),
                            'URL': 'https://www.d2b.go.kr'
                        })
            except: continue

        # --- 4. 가스공사 (유지) ---
        # (이전 가스공사 로직 유지)

        # --- 최종 출력 ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 수색 완료! 국방부를 포함하여 총 {len(df)}건을 발견했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='RADAR_REPORT')
            st.download_button(label="📥 엑셀 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_{today_str}.xlsx")
        else:
            st.warning("⚠️ 검색된 공고가 없습니다.")
            
        st.session_state.clicked = False 
        
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
        st.session_state.clicked = False
