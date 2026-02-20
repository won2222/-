import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re

# --- [1] 부장님 v169.0 설정 복제 ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
            "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v4000", layout="wide")
st.title("📡 THE RADAR v4000.0")
st.info("🎯 부장님 v169.0 데이터 추출 로직(or 연산자 체인) 100% 동기화")

if st.sidebar.button("🚀 부장님 로직 강제 수색 개시", type="primary"):
    final_list = []
    now = datetime.now()
    today_api = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=4)).strftime("%Y%m%d")
    
    status_st = st.empty()

    try:
        # --- 🎯 [부장님 필살기: 국방부 D2B 로직] ---
        for bt in ['bid', 'priv']:
            status_st.info(f"📡 국방부 {bt} 채널 분석 중...")
            url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
            
            try:
                # 부장님 코드와 동일한 타임아웃 10초 적용
                res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, headers=HEADERS, timeout=10).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                
                for it in items_d:
                    # 🎯 부장님 방식: 이름과 마감일 추출 (or 연산자 활용)
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')
                    
                    # 🎯 부장님 방식: 날짜 비교 조건문 완벽 복제
                    if any(kw in bid_nm for kw in KEYWORDS) and (bt=='priv' or (today_api <= str(clos_dt)[:8] <= target_end_day)):
                        
                        # 🎯 부장님 방식: 예산 및 참조번호 우선순위 추출
                        budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                        p_no = it.get('pblancNo') or it.get('dcsNo') # 이게 핵심입니다.
                        
                        # 상세 정보 보강 (부장님 v169.0 방식)
                        try:
                            det_url = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancDetail' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanDetail'}"
                            p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'), 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                            if bt == 'priv': p_det.update({'iemNo': it.get('iemNo'), 'ntatPlanDate': it.get('ntatPlanDate')})
                            
                            det_res = requests.get(det_url, params=p_det, timeout=5).json()
                            det_item = det_res.get('response', {}).get('body', {}).get('item', {})
                            budget = det_item.get('budgetAmount') or budget
                            p_no = det_item.get('g2bPblancNo') or p_no
                        except: pass

                        final_list.append({
                            '출처': f'D2B({bt})',
                            '번호': p_no,
                            '공고명': bid_nm,
                            '수요기관': it.get('ornt'),
                            '예산': int(pd.to_numeric(budget, errors='coerce') or 0),
                            '마감일시': clean_date_strict(clos_dt),
                            '상세URL': 'https://www.d2b.go.kr'
                        })
            except: pass

        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일시'])
            st.success(f"✅ 작전 완료! 부장님 로직 동기화로 {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            # 엑셀 다운로드 동일
        else:
            st.warning("⚠️ 결과가 없습니다. 키워드 매칭이나 날짜 범위를 다시 확인해 보세요.")

    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
