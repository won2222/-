import streamlit as st
import requests
import pandas as pd
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import time
import pytz

# --- [1] 부장님 v169.0 정예 설정 및 헤더 강화 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')

# 서버가 브라우저 접속으로 착각하게 만드는 강화된 헤더
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Connection': 'keep-alive'
}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
            "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]

MUST_PASS = ['경기도', '평택시', '화성시', '서울특별시', '서울', '인천', '전국']

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v3700", layout="wide")
st.title("📡 THE RADAR v3700.0")
st.error("🚀 국방부(D2B) 서버 응답 강제 유도 모드 (인내심 수색 가동)")

if st.sidebar.button("🛡️ 국방부 서버 강제 돌파 수색", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # v169 날짜 로직
    today_disp = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=4)).strftime("%Y%m%d")
    
    status_st = st.empty()
    log_st = st.expander("🛠️ 침투 시도 로그", expanded=True)

    try:
        # --- 🎯 [v169.0 국방부 강제 돌파 로직] ---
        for bt in ['bid', 'priv']:
            status_st.info(f"📡 국방부 {bt} 채널에 정밀 침투 시도 중... (최대 40초 대기)")
            
            try:
                list_url = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
                
                # 🎯 조치 1: Timeout을 40초로 대폭 늘려 서버가 응답할 때까지 버팁니다.
                # 🎯 조치 2: verify=False를 통해 SSL 보안 인증 지연을 건너뜁니다.
                res_d = requests.get(list_url, 
                                     params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, 
                                     headers=HEADERS, 
                                     timeout=40).json()
                
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                
                if not items_d:
                    log_st.warning(f"⚠️ 국방부 {bt}: 연결은 성공했으나 데이터가 비어있습니다.")
                    continue

                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')
                    
                    if any(kw in bid_nm for kw in KEYWORDS) and (bt=='priv' or (today_disp <= str(clos_dt)[:8] <= target_end_day)):
                        
                        # 🎯 v169 예산 복구 로직 가동
                        det_url = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancDetail' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanDetail'}"
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'), 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if bt == 'priv': p_det.update({'iemNo': it.get('iemNo'), 'ntatPlanDate': it.get('ntatPlanDate')})
                        
                        try:
                            # 상세 정보도 인내심 있게 기다림
                            det_item = requests.get(det_url, params=p_det, headers=HEADERS, timeout=20).json().get('response', {}).get('body', {}).get('item', {})
                            p_no = det_item.get('g2bPblancNo') or it.get('pblancNo') or it.get('dcsNo')
                            budget = det_item.get('budgetAmount') or it.get('asignBdgtAmt') or 0
                            area = det_item.get('areaLmttList') or "상세확인"
                        except:
                            p_no = it.get('pblancNo') or it.get('dcsNo')
                            budget = it.get('asignBdgtAmt') or 0
                            area = "목록확인"

                        final_list.append({
                            '출처': f'D2B({bt})', '번호': p_no, '공고명': bid_nm, '수요기관': it.get('ornt'), 
                            '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': area, 
                            '마감일': clean_date_strict(clos_dt), 'URL': 'https://www.d2b.go.kr'
                        })
                        log_st.success(f"✅ 포착: {bid_nm[:20]}...")

            except Exception as e:
                log_st.error(f"❌ 국방부 {bt} 채널 침투 실패: 서버가 응답을 거부했습니다. (에러: {e})")

        # --- [결과 출력] ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 작전 완료! 국방부 장애를 뚫고 총 {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 국방부 돌파 리포트 저장", data=output.getvalue(), file_name=f"D2B_FORCE_RADAR_{today_disp}.xlsx")
        else:
            st.warning("⚠️ 서버 상태 악화로 인해 국방부 공고를 단 한 건도 가져오지 못했습니다. 잠시 후 재시도 바랍니다.")

    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
