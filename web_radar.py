import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import io
import re
import pytz # 🎯 시차 해결을 위한 필수 라이브러리

# --- [1] 부장님 v169.0 설정 및 시차 보정 ---
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
st.set_page_config(page_title="THE RADAR v4100", layout="wide")
st.title("📡 THE RADAR v4100.0")
st.error("🚀 서버 시차(KST) 강제 보정 완료: 부장님 v169.0 추출 엔진 가동")

if st.sidebar.button("🛡️ 시차 보정 후 국방부 재공격", type="primary"):
    final_list = []
    
    # 🎯 [핵심] 서버 시차 해결: 무조건 한국 시간으로 고정
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST) # 👈 서버 시간이 아닌 '한국 현재 시간' 기준
    
    # 부장님 v169.0 날짜 계산 방식
    today_api = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=7)).strftime("%Y%m%d") # 4일에서 7일로 확장(안전장치)
    
    status_st = st.empty()

    try:
        # --- [국방부 D2B 정밀 타격] ---
        for bt in ['bid', 'priv']:
            status_st.info(f"📡 국방부 {bt} 채널 분석 중... (기준일: {today_api})")
            url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
            
            try:
                res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, headers=HEADERS, timeout=15).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')
                    
                    # 🎯 부장님 v169.0 비교문 + 시차 보정된 today_api
                    if any(kw in bid_nm for kw in KEYWORDS):
                        # 수의계약(priv)은 무조건 통과, 일반(bid)은 날짜 범위 체크
                        if bt == 'priv' or (today_api <= str(clos_dt)[:8] <= target_end_day):
                            
                            # 부장님 방식 예산 및 번호 추출
                            budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                            p_no = it.get('pblancNo') or it.get('dcsNo')
                            
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
                                '출처': f'D2B({bt})', '번호': p_no, '공고명': bid_nm, '수요기관': it.get('ornt'),
                                '예산': int(pd.to_numeric(budget, errors='coerce') or 0),
                                '마감일시': clean_date_strict(clos_dt), 'URL': 'https://www.d2b.go.kr'
                            })
            except Exception as e:
                st.warning(f"⚠️ {bt} 채널 접속 중 오류 발생 (스킵)")

        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일시'])
            st.success(f"✅ 작전 완료! 시차 오류를 극복하고 {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            # 엑셀 저장 생략
        else:
            st.warning(f"⚠️ {today_api} 기준, 부장님 키워드와 일치하는 국방부 공고가 없습니다. (서버 시간 보정 완료)")

    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
