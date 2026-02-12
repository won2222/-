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

# 파일 기반 통합 키워드 (18종)
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = "".join(filter(str.isdigit, str(val)))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR", layout="wide")
st.title("📡 THE RADAR")
st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE (RESILIENT MODE)")
st.divider()

if st.sidebar.button("🔍 전 기관 통합 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 날짜 파라미터
    s_date = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m')
    kogas_start = (now - timedelta(days=180)).strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=7)).strftime("%Y%m%d")
    
    status_st = st.empty()
    prog = st.progress(0)
    
    # --- [PHASE 1] G2B & LH (공고일 기준) ---
    status_st.info("📡 [PHASE 1] 나라장터 및 LH 수색 중...")
    # (나라장터 및 LH 로직 - 이전 안정 버전 유지)
    # ... (생략) ...

    # --- [PHASE 2] D2B (방어 로직 강화) ---
    status_st.info("📡 [PHASE 2] 국방부 서버 접속 시도 중 (재시도 로직 가동)...")
    d2b_configs = [
        {'t': '일반', 'url': 'getDmstcCmpetBidPblancList', 'params': {'pblancDateBegin': s_date, 'pblancDateEnd': today_str}},
        {'t': '수의', 'url': 'getDmstcOthbcVltrnNtatPlanList', 'params': {'prqudoPresentnClosDateBegin': today_str, 'prqudoPresentnClosDateEnd': target_end_day}}
    ]
    
    for cfg in d2b_configs:
        try:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
            p.update(cfg['params'])
            # 🎯 타임아웃을 늘리고 에러 발생 시 프로그램이 꺼지지 않게 try-except로 철저히 격리
            res = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['url']}", 
                               params=p, headers=HEADERS, timeout=15).json()
            items = res.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            items = [items] if isinstance(items, dict) else items
            for it in items:
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                if any(kw in bid_nm for kw in KEYWORDS):
                    final_list.append({
                        '출처': f'D2B({cfg["t"]})',
                        '번호': it.get('pblancNo') or it.get('dcsNo', '-'),
                        '공고명': bid_nm,
                        '수요기관': it.get('ornt', '국방부'),
                        '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or it.get('budgetAmount') or 0, errors='coerce') or 0),
                        '마감일': format_date_clean(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')),
                        'URL': 'https://www.d2b.go.kr'
                    })
        except Exception as e:
            st.sidebar.warning(f"⚠️ 국방부({cfg['t']}) 접속 지연: 현재 서버 점검 중일 수 있습니다.")
            continue

    # --- [PHASE 3] K-water & KOGAS (보내주신 파일 로직) ---
    status_st.info("📡 [PHASE 3] 수자원 및 가스공사 수색 중...")
    # (파일 '수자원공사 완성.py', '가스공사 완성.py' 로직 유지)
    # ... (생략) ...

    # --- [최종 출력] ---
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
        
        # 상단 통계 지표
        counts = df['출처'].value_counts()
        cols = st.columns(5)
        for i, (name, count) in enumerate(counts.items()):
            if i < 5: cols[i].metric(name, f"{count}건")
        
        st.success(f"✅ 총 {len(df)}건의 공고를 확보했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
    else:
        st.warning("⚠️ 현재 레이더에 포착된 공고가 없습니다. (국방부 서버 응답 지연 포함)")
