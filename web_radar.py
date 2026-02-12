import streamlit as st
import requests
import pandas as pd
from urllib.parse import unquote
from datetime import datetime, timedelta
import pytz
import io

# --- [1] 부장님 정예 세팅 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 파일 기준 키워드 (18종)
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
            "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = "".join(filter(str.isdigit, str(val)))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 ---
st.set_page_config(page_title="THE RADAR", layout="wide")
st.title("📡 THE RADAR (D2B Test Mode)")
st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE - PHASE: D2B")
st.divider()

if st.sidebar.button("🔍 국방부(D2B) 단독 수색", type="primary"):
    d2b_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 🎯 국방부 마감일 기준 수색 범위 (오늘 ~ 향후 7일)
    today_str = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=7)).strftime("%Y%m%d")
    
    status_st = st.empty()
    status_st.info("📡 [PHASE: D2B] 국방부 수의계약/일반입찰 서버 접속 중...")
    
    try:
        # 🎯 국방부 수의계약 (마감일 기준 정밀 타격)
        p_priv = {
            'serviceKey': SERVICE_KEY,
            'numOfRows': '500',
            '_type': 'json',
            'prqudoPresentnClosDateBegin': today_str,
            'prqudoPresentnClosDateEnd': target_end_day
        }
        
        res_priv = requests.get("http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList", params=p_priv, timeout=10).json()
        items_priv = res_priv.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        items_priv = [items_priv] if isinstance(items_priv, dict) else items_priv
        
        for it in items_priv:
            bid_nm = it.get('othbcNtatNm', '')
            if any(kw in bid_nm for kw in KEYWORDS):
                d2b_list.append({
                    '출처': 'D2B(수의)',
                    '번호': it.get('dcsNo', '-'),
                    '공고명': bid_nm,
                    '수요기관': it.get('ornt', '국방부'),
                    '마감일': format_date_clean(it.get('prqudoPresentnClosDt')),
                    'URL': 'https://www.d2b.go.kr'
                })

        # 🎯 국방부 일반경쟁 (파일 내 v161.0 로직 반영)
        p_gen = {
            'serviceKey': SERVICE_KEY,
            'numOfRows': '300',
            '_type': 'json',
            'pblancDateBegin': (now - timedelta(days=14)).strftime("%Y%m%d"), # 넉넉히 2주 전 공고까지
            'pblancDateEnd': today_str
        }
        res_gen = requests.get("http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList", params=p_gen, timeout=10).json()
        items_gen = res_gen.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        items_gen = [items_gen] if isinstance(items_gen, dict) else items_gen

        for it in items_gen:
            bid_nm = it.get('bidNm', '')
            if any(kw in bid_nm for kw in KEYWORDS):
                d2b_list.append({
                    '출처': 'D2B(일반)',
                    '번호': it.get('pblancNo', '-'),
                    '공고명': bid_nm,
                    '수요기관': it.get('ornt', '국방부'),
                    '마감일': format_date_clean(it.get('biddocPresentnClosDt')),
                    'URL': 'https://www.d2b.go.kr'
                })

        # 결과 출력
        if d2b_list:
            df = pd.DataFrame(d2b_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 국방부 수색 완료! 총 {len(df)}건을 발견했습니다.")
            st.dataframe(df, use_container_width=True)
            
            # 다운로드 버튼
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='D2B_TEST')
            st.download_button(label="📥 국방부 테스트 리포트 다운로드", data=output.getvalue(), file_name=f"D2B_TEST_{today_str}.xlsx")
        else:
            st.warning("⚠️ 현재 국방부 서버에 조건(키워드 18종)에 부합하는 공고가 없습니다.")
            
    except Exception as e:
        st.error(f"🚨 국방부 서버 응답 지연 또는 오류: {e}")
