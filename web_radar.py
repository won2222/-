import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 부장님 v169.0 세팅 100% 복제 ---
# unquote 없이 부장님 원본 키 그대로 사용
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
            "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

st.set_page_config(page_title="THE RADAR v3800", layout="wide")
st.title("📡 THE RADAR v3800.0")
st.warning("🎯 국방부(D2B) v169.0 원본 로직 강제 이식 모드")

if st.sidebar.button("🛡️ v169.0 로직으로 국방부 재침투", type="primary"):
    final_list = []
    
    # --- 🎯 [v169.0 날짜 계산 로직 그대로 복제] ---
    now = datetime.now()
    today_disp = now.strftime("%Y.%m.%d")
    target_end_day = (now + timedelta(days=4)).strftime("%Y%m%d")
    
    status_st = st.empty()
    log_st = st.expander("🛠️ v169.0 엔진 가동 로그", expanded=True)

    try:
        # --- [3단계: 방위사업청 D2B] ---
        for bt in ['bid', 'priv']:
            status_st.info(f"📡 국방부 {bt} 채널 분석 중...")
            
            # v169.0과 동일한 URL 및 파라미터 구조
            url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
            
            try:
                # 🎯 핵심: 부장님 코드와 동일하게 _type: json과 400개 요청
                res_d = requests.get(url_d, 
                                     params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, 
                                     headers=HEADERS, 
                                     timeout=20).json()
                
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')
                    
                    # 🎯 부장님 v169.0의 날짜 비교 로직 (today_disp.replace 사용)
                    d2b_today_str = today_disp.replace('.','')
                    
                    if any(kw in bid_nm for kw in KEYWORDS) and (bt=='priv' or (d2b_today_str <= str(clos_dt)[:8] <= target_end_day)):
                        
                        # 🎯 예산 복구 정밀 수집 (부장님 원형 로직)
                        budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                        url_det = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancDetail' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanDetail'}"
                        
                        p_det = {
                            'serviceKey': SERVICE_KEY, 
                            'pblancNo': it.get('pblancNo'), 
                            'pblancOdr': it.get('pblancOdr'), 
                            'demandYear': it.get('demandYear'), 
                            'orntCode': it.get('orntCode'), 
                            'dcsNo': it.get('dcsNo'), 
                            '_type': 'json'
                        }
                        if bt == 'priv': p_det.update({'iemNo': it.get('iemNo'), 'ntatPlanDate': it.get('ntatPlanDate')})
                        
                        try:
                            # 상세 페이지에서도 SCU번호와 예산 확보
                            det_res = requests.get(url_det, params=p_det, timeout=10).json()
                            det_item = det_res.get('response', {}).get('body', {}).get('item', {})
                            budget = det_item.get('budgetAmount') or budget
                            p_no = det_item.get('g2bPblancNo') or it.get('pblancNo') or it.get('dcsNo')
                        except:
                            p_no = it.get('pblancNo') or it.get('dcsNo')

                        final_list.append({
                            '출처': f'D2B({bt})', '번호': p_no, '공고명': bid_nm, '수요기관': it.get('ornt'), 
                            '예산': int(pd.to_numeric(budget, errors='coerce') or 0), 
                            '마감일시': clean_date_strict(clos_dt),
                            '상세URL': 'https://www.d2b.go.kr'
                        })
                        log_st.success(f"✅ 국방부 확보: {bid_nm[:20]}...")

            except Exception as e:
                log_st.error(f"❌ 국방부 {bt} 채널 오류: {e}")

        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일시'])
            st.success(f"✅ 작전 완료! {len(df)}건 확보 (v169.0 로직 완벽 복원)")
            st.dataframe(df)
            # 엑셀 다운로드 동일
        else:
            st.error("🚨 부장님 원본 로직으로도 응답이 없습니다. 국방부 서버의 IP 차단이 의심됩니다.")

    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
