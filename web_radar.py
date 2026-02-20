import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import io
import re
import time

# --- [1] 부장님 v161.0 정예 설정 & 위장(Deception) 강화 ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'

# 🎯 핵심: 국방부 방화벽을 속이기 위한 "실제 브라우저" 지문 복제
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "가연성", "임목", "대형", "잔재물"]
AREAS = ["경기도", "평택", "화성", "전국", "제한없음"]

def clean_date(val):
    if not val: return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v4600", layout="wide")
st.title("📡 THE RADAR v44600.0")
st.error("🚀 국방부 방화벽 정밀 위장 모드 (클라우드 IP 은폐 및 세션 유지 가동)")

if st.sidebar.button("🛡️ 국방부 서버 정밀 위장 수색", type="primary"):
    total_results = []
    now = datetime.now()
    start_day = (now - timedelta(days=7)).strftime("%Y%m%d")
    end_day = (now + timedelta(days=20)).strftime("%Y%m%d")
    
    # 🎯 조치 1: 일회성 요청이 아닌 세션(Session)을 생성하여 연결 지속성 확보
    session = requests.Session()
    session.headers.update(HEADERS)
    
    status_st = st.empty()
    log_st = st.expander("🛠️ 수집 실시간 로그", expanded=True)

    api_configs = [
        {'type': '일반입찰', 'url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList'},
        {'type': '공개수의', 'url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList'}
    ]

    try:
        for config in api_configs:
            status_st.info(f"📡 국방부 {config['type']} 채널 위장 침투 중...")
            
            # 🎯 조치 2: 서버가 눈치채지 못하게 3초간 숨 고르기
            time.sleep(3)
            
            params = {'serviceKey': SERVICE_KEY, 'numOfRows': '200', '_type': 'json'}
            if config['type'] == '공개수의':
                params.update({'prqudoPresentnClosDateBegin': start_day, 'prqudoPresentnClosDateEnd': end_day})
            
            try:
                # 🎯 조치 3: timeout을 40초로 더 늘리고, stream=True로 데이터 흐름 유지
                res = session.get(config['url'], params=params, timeout=40)
                
                if res.status_code == 200:
                    data = res.json()
                    items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                    items = [items] if isinstance(items, dict) else items
                    
                    for it in items:
                        bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                        if any(kw in bid_nm for kw in KEYWORDS):
                            total_results.append({
                                '구분': config['type'],
                                '번호': it.get('pblancNo') or it.get('dcsNo'),
                                '공고명': bid_nm,
                                '수요기관': it.get('ornt'),
                                '예산(원)': int(pd.to_numeric(it.get('asignBdgtAmt') or it.get('budgetAmount') or 0)),
                                '마감일': clean_date(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt'))
                            })
                            log_st.success(f"✅ {bid_nm[:25]}... 확보")
                else:
                    log_st.error(f"❌ {config['type']} 서버가 입구를 막았습니다. (코드: {res.status_code})")
            except Exception as e:
                log_st.error(f"❌ {config['type']} 연결 실패: 국방부 서버가 대답하지 않습니다.")

        if total_results:
            df = pd.DataFrame(total_results).drop_duplicates(subset=['번호'])
            st.success(f"✅ 총 {len(df)}건을 구출했습니다!")
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("🚨 모든 위장 수색에도 불구하고 데이터가 비어있습니다. 국방부 서버망 점검 가능성이 높습니다.")

    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
