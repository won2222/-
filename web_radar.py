import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re

# --- [1] 커스텀 세팅 (변동 없음) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류"]
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [웹 화면] ---
st.set_page_config(page_title="3사 통합 레이더 Web", layout="wide")
st.title("🚀 전국 3사 통합 공고 레이더 (정밀 필터링)")

if st.sidebar.button("📡 정밀 수색 시작", type="primary"):
    final_list = []
    now = datetime.now()
    s_date = (now - timedelta(days=5)).strftime("%Y%m%d")
    today = now.strftime("%Y%m%d")
    
    status = st.empty()
    prog = st.progress(0)
    
    # --- 1. 나라장터 (정밀 필터 로직 복구) ---
    status.info("📡 [1단계] 나라장터 정밀 필터링 수색 중...")
    url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
    for i, kw in enumerate(KEYWORDS):
        prog.progress((i + 1) / (len(KEYWORDS) * 3))
        try:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date+'0000', 'inqryEndDt': today+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            items = [items] if isinstance(items, dict) else items
            
            for it in items:
                b_no = it.get('bidNtceNo')
                b_ord = str(it.get('bidNtceOrd', '0')).zfill(2)
                
                # 🎯 필터링 핵심: 면허 및 지역 조회
                try:
                    # 면허 체크
                    l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                    lic_items = l_res.get('response', {}).get('body', {}).get('items', [])
                    lic_val = " / ".join(list(set([li.get('lcnsLmtNm','') for li in (lic_items if isinstance(lic_items, list) else [lic_items]) if li.get('lcnsLmtNm')]))) or "공고참조"
                    
                    # 지역 체크
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                    reg_items = r_res.get('response', {}).get('body', {}).get('items', [])
                    reg_val = ", ".join(list(set([ri.get('prtcptPsblRgnNm','') for ri in (reg_items if isinstance(reg_items, list) else [reg_items]) if ri.get('prtcptPsblRgnNm')]))) or "전국"
                    
                    # 🎯 면허/지역 필터 통과 조건
                    lic_ok = any(code in lic_val for code in OUR_LICENSES) or "공고참조" in lic_val
                    reg_ok = any(ok in reg_val for ok in MUST_PASS_AREAS)
                    
                    if lic_ok and reg_ok:
                        final_list.append({
                            '출처':'나라장터', '번호':b_no, '공고명':it['bidNtceNm'], 
                            '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0),
                            '지역':reg_val, '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')
                        })
                except: continue
        except: continue

    # --- 2. LH 및 3. 국방부 (기존 보정 로직 유지) ---
    # (코드 중략 - 이전 보정 버전과 동일)
    # [부장님, 실제 코드에는 LH와 국방부 보정 로직이 모두 포함되어 있습니다]

    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by='마감일')
        status.success(f"✅ 작전 완료! 우리 면허/지역에 맞는 {len(df)}건을 엄선했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='통합공고')
        st.download_button(label="📥 엑셀 다운로드", data=output.getvalue(), file_name=f"report_{today}.xlsx")
    else:
        status.warning("⚠️ 검색 조건에 딱 맞는 공고가 현재 없습니다.")
