import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import io
import re

# --- [1] 부장님 v161.0 설정 및 로직 복제 ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS = ["폐기물", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "음식물"]
AREAS = ["경기도", "평택시", "화성시", "제한없음", "전국"]

def format_d2b_date(date_val):
    if not date_val: return "-"
    date_str = str(date_val).replace(".0", "").strip()
    if len(date_str) >= 12: return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {date_str[8:10]}:{date_str[10:12]}"
    elif len(date_str) >= 8: return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v4300", layout="wide")
st.title("📡 THE RADAR v4300.0")
st.success("🎯 부장님 v161.0 국방부 전용 엔진(수의+일반 통합) 이식 완료")

if st.sidebar.button("🚀 국방부 v161 로직 수색 개시", type="primary"):
    total_results = []
    today_dt = datetime.now()
    start_day = (today_dt - timedelta(days=10)).strftime("%Y%m%d")
    end_day = (today_dt + timedelta(days=20)).strftime("%Y%m%d")
    
    status_st = st.empty()
    
    # 🎯 [v161.0 API 설정 복제]
    api_configs = [
        {'type': '일반입찰', 'list_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList', 'det_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancDetail'},
        {'type': '공개수의', 'list_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList', 'det_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanDetail'}
    ]

    try:
        for config in api_configs:
            status_st.info(f"🔍 국방부 {config['type']} 데이터 스캔 중...")
            params = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
            # 🎯 수의계약 전용 날짜 파라미터 적용 (v161 핵심)
            if config['type'] == '공개수의':
                params.update({'prqudoPresentnClosDateBegin': start_day, 'prqudoPresentnClosDateEnd': end_day})
            
            res = requests.get(config['list_url'], params=params, headers=HEADERS, timeout=15)
            if res.status_code == 200:
                items = res.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items = [items] if isinstance(items, dict) else items
                
                for it in items:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in KEYWORDS):
                        # 🎯 v161 전용 참조번호 조합 로직
                        p_no = it.get('pblancNo')
                        d_year = str(it.get('demandYear', ''))
                        d_no = str(it.get('dcsNo', ''))
                        p_prefix = "".join([c for c in str(p_no) if c.isalpha()])
                        combined_g2b = f"{d_year}{p_prefix}{d_no}"

                        # 🎯 v161 전용 상세 조회 파라미터
                        p_det = {
                            'serviceKey': SERVICE_KEY, 'pblancNo': p_no, 
                            'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0],
                            'demandYear': d_year, 'orntCode': it.get('orntCode'), 'dcsNo': d_no, '_type': 'json'
                        }
                        if config['type'] == '공개수의':
                            p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})

                        area, budget = "제한없음", 0
                        try:
                            det_res = requests.get(config['det_url'], params=p_det, headers=HEADERS, timeout=5).json()
                            det_data = det_res.get('response', {}).get('body', {}).get('item', {})
                            if isinstance(det_data, dict):
                                area = det_data.get('areaLmttList') or "제한없음"
                                combined_g2b = det_data.get('g2bPblancNo') or combined_g2b
                                # 🎯 예산 데이터 3중 필터 (v161 핵심)
                                budget = det_data.get('budgetAmount') or it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                        except: pass

                        status = it.get('progrsSttus') or "진행중"
                        if ("진행중" in status or status == "") and any(t in area for t in AREAS):
                            total_results.append({
                                '구분': config['type'],
                                '통합참조번호': combined_g2b,
                                '공고명': bid_nm,
                                '수요기관': it.get('ornt'),
                                '지역제한': area,
                                '예산(원)': int(pd.to_numeric(budget, errors='coerce') or 0),
                                '마감일시': format_d2b_date(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt'))
                            })

        status_st.empty()
        if total_results:
            df = pd.DataFrame(total_results).sort_values(by='마감일시')
            st.success(f"✅ 국방부 수색 완료! {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산(원)': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 v161 통합 리포트 저장", data=output.getvalue(), file_name=f"D2B_v161_{start_day}.xlsx")
        else:
            st.warning("⚠️ v161 로직으로도 현재 조건에 맞는 국방부 공고가 없습니다.")
            
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
