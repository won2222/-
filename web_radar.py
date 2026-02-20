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

# --- [1] 부장님 v169.0 정예 설정 엔진 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
            "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]

MUST_PASS = ['경기도', '평택시', '화성시', '서울특별시', '서울', '인천', '전국']
EXCLUDE_LIST = ['충청', '전라', '강원', '경상', '제주', '부산', '대구', '광주', '대전', '울산', '세종', '충북', '충남', '경북', '경남', '전북', '전남']

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v3600", layout="wide")
st.title("📡 THE RADAR v3600.0")
st.info("🎯 국방부(D2B) v169.0 정밀 추적 엔진 이식 완료")

if st.sidebar.button("🚀 국방부 정밀 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # v169 날짜 로직
    s_date_api = (now - timedelta(days=4)).strftime("%Y%m%d")
    today_disp = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=4)).strftime("%Y%m%d")
    
    status_st = st.empty()
    
    try:
        # --- 🎯 [핵심] 3단계: 방위사업청(D2B) 부장님 정밀 로직 ---
        status_st.info("📡 [국방부] 예산 및 참조번호 정밀 추적 중...")
        
        # 'bid'(일반입찰)와 'priv'(공개수의) 두 채널 모두 타격
        for bt in ['bid', 'priv']:
            try:
                list_url = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
                res_d = requests.get(list_url, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, headers=HEADERS, timeout=15).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')
                    
                    # 키워드 매칭 및 날짜 범위 검증 (부장님 v169 로직)
                    if any(kw in bid_nm for kw in KEYWORDS) and (bt=='priv' or (today_disp <= str(clos_dt)[:8] <= target_end_day)):
                        
                        # 🎯 v169 핵심: 상세 페이지 API 침투 (예산 복구)
                        budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                        det_url = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancDetail' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanDetail'}"
                        
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
                            # 🎯 상세 API에서 budgetAmount와 g2bPblancNo(통합참조번호) 탈취
                            det_res = requests.get(det_url, params=p_det, timeout=10).json()
                            det_item = det_res.get('response', {}).get('body', {}).get('item', {})
                            budget = det_item.get('budgetAmount') or budget
                            p_no = det_item.get('g2bPblancNo') or it.get('pblancNo') or it.get('dcsNo')
                        except:
                            p_no = it.get('pblancNo') or it.get('dcsNo')

                        final_list.append({
                            '출처': f'D2B({bt})', 
                            '번호': p_no, 
                            '공고명': bid_nm, 
                            '수요기관': it.get('ornt'), 
                            '예산': int(pd.to_numeric(budget, errors='coerce') or 0), 
                            '지역': '상세확인', 
                            '마감일': clean_date_strict(clos_dt), 
                            'URL': 'https://www.d2b.go.kr'
                        })
            except Exception as e:
                st.warning(f"⚠️ 국방부 {bt} 채널 일시적 응답 지연: {e}")

        # --- [최종 출력] ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 국방부 수색 완료! v169.0 로직으로 {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 국방부 정밀 리포트 저장", data=output.getvalue(), file_name=f"D2B_v169_RADAR_{today_disp}.xlsx")
        else:
            st.warning("⚠️ 현재 조건에 맞는 국방부 공고가 없습니다. (서버 상태 확인 필요)")

    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
