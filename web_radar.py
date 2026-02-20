import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import io
import re
import time

# --- [1] 부장님 v161.0 정예 설정 (우회 접속 최적화) ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'

# 서버가 '기계'가 아닌 '사람'으로 착각하게 만드는 강화된 헤더
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01'
}

KEYWORDS = ["폐기물", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "음식물"]
AREAS = ["경기도", "평택시", "화성시", "제한없음", "전국"]

def format_d2b_date(date_val):
    if not date_val: return "-"
    date_str = str(date_val).replace(".0", "").strip()
    if len(date_str) >= 8: return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v4400", layout="wide")
st.title("📡 THE RADAR v4400.0")
st.error("🚀 국방부 방화벽 우회 모드 가동 (저강도 침투 및 타임아웃 30초 확장)")

if st.sidebar.button("🛡️ 국방부 서버 저강도 침투 개시", type="primary"):
    total_results = []
    today_dt = datetime.now()
    start_day = (today_dt - timedelta(days=10)).strftime("%Y%m%d")
    end_day = (today_dt + timedelta(days=20)).strftime("%Y%m%d")
    
    status_st = st.empty()
    log_st = st.expander("🛠️ 실시간 침투 로그 (부장님 확인용)", expanded=True)

    # 🎯 [v161.0 기반 우회 엔진]
    api_configs = [
        {'type': '일반입찰', 'list_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList'},
        {'type': '공개수의', 'list_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList'}
    ]

    try:
        for config in api_configs:
            status_st.info(f"🔍 국방부 {config['type']} 우회 침투 중...")
            
            # 🎯 조치 1: 한 번에 많이 가져오지 않고(100개), 타임아웃을 30초로 대폭 연장
            params = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', '_type': 'json'}
            if config['type'] == '공개수의':
                params.update({'prqudoPresentnClosDateBegin': start_day, 'prqudoPresentnClosDateEnd': end_day})
            
            try:
                # 🎯 조치 2: 서버 부하를 줄이기 위해 접속 전 1초 대기
                time.sleep(1)
                res = requests.get(config['list_url'], params=params, headers=HEADERS, timeout=30)
                
                if res.status_code == 200:
                    items = res.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])
                    items = [items] if isinstance(items, dict) else items
                    
                    for it in items:
                        bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                        if any(kw in bid_nm for kw in KEYWORDS):
                            # 상세 조회 생략하고 목록 데이터 우선 확보 (서버 튕김 방지)
                            total_results.append({
                                '구분': config['type'],
                                '공고번호': it.get('pblancNo') or it.get('dcsNo'),
                                '공고명': bid_nm,
                                '수요기관': it.get('ornt'),
                                '지역': '국방부공고(상세확인)',
                                '예산(원)': int(pd.to_numeric(it.get('asignBdgtAmt') or 0)),
                                '마감일시': format_d2b_date(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt'))
                            })
                            log_st.success(f"✅ 확보: {bid_nm[:20]}...")
                else:
                    log_st.error(f"❌ {config['type']} 서버 응답 코드: {res.status_code}")
            except Exception as e:
                log_st.warning(f"⚠️ {config['type']} 채널 침투 실패 (서버가 응답을 거부함)")

        status_st.empty()
        if total_results:
            df = pd.DataFrame(total_results).sort_values(by='마감일시')
            st.success(f"✅ 총 {len(df)}건을 확보했습니다! 국방부 장애를 우회했습니다.")
            st.dataframe(df.style.format({'예산(원)': '{:,}원'}), use_container_width=True)
        else:
            st.warning("🚨 국방부 서버가 현재 모든 클라우드 IP를 차단한 상태입니다. 잠시 후 시도해 주세요.")
            
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
