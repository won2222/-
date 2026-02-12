import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import io
import pytz

# --- [1] 국방부 전용 설정 (부장님 v161.0 로직 100% 이식) ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 🎯 부장님 타겟 키워드 및 지역 필터
TARGET_KEYWORDS = ["폐기물", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "음식물"]
TARGET_AREAS = ["경기도", "평택시", "화성시", "제한없음", "전국"]

def format_d2b_date(date_val):
    if not date_val: return "-"
    date_str = str(date_val).replace(".0", "").strip()
    try:
        if len(date_str) >= 12: return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {date_str[8:10]}:{date_str[10:12]}"
        elif len(date_str) >= 8: return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str
    except: return date_str

# --- [2] 웹 화면 구성 ---
st.set_page_config(page_title="D2B 전용 테스트", layout="wide")
st.title("📡 D2B 정밀 타격 테스트 유닛")
st.write("📍 **필터:** v161.0 로직 적용 (상세 페이지 2차 파싱 모드)")
st.divider()

# 사이드바: 수색 범위 조절
st.sidebar.header("🕹️ 수색 범위 설정")
search_days = st.sidebar.slider("조회 과거/미래 범위 (일)", 1, 30, 10)

if st.sidebar.button("🔍 국방부 단독 정밀 수색 시작", type="primary"):
    total_results = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # v161.0 날짜 동기화
    start_day = (now - timedelta(days=search_days)).strftime("%Y%m%d")
    end_day = (now + timedelta(days=search_days)).strftime("%Y%m%d")
    
    st.write(f"⏱️ **수색 시점:** `{now.strftime('%Y-%m-%d %H:%M:%S')}`")
    st.info(f"📅 **조회 기간:** {start_day} ~ {end_day}")

    api_configs = [
        {
            'type': '일반입찰',
            'list_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList',
            'det_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancDetail',
            'clos': 'biddocPresentnClosDt'
        },
        {
            'type': '공개수의',
            'list_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList',
            'det_url': 'http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanDetail',
            'clos': 'prqudoPresentnClosDt'
        }
    ]

    prog_bar = st.progress(0)
    status_msg = st.empty()

    for idx, config in enumerate(api_configs):
        status_msg.info(f"🔍 [{config['type']}] 데이터 스캔 및 상세 분석 중...")
        prog_bar.progress((idx + 1) / 2)
        
        params = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
        if config['type'] == '공개수의':
            params.update({'prqudoPresentnClosDateBegin': start_day, 'prqudoPresentnClosDateEnd': end_day})
        
        try:
            res = requests.get(config['list_url'], params=params, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                items = res.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items = [items] if isinstance(items, dict) else items
                
                for it in items:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in TARGET_KEYWORDS):
                        # 🎯 v161.0 핵심: 상세 조회를 위한 파라미터 구성 (정밀 오타 수정)
                        p_no = it.get('pblancNo')
                        d_year = str(it.get('demandYear', ''))
                        d_no = str(it.get('dcsNo', ''))
                        
                        p_det = {
                            'serviceKey': SERVICE_KEY, 
                            'pblancNo': p_no, 
                            'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0],
                            'demandYear': d_year, 
                            'orntCode': it.get('orntCode'), 
                            'dcsNo': d_no, 
                            '_type': 'json'
                        }
                        if config['type'] == '공개수의':
                            p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})

                        area = "제한없음"
                        budget = 0
                        combined_g2b = p_no
                        
                        # 🎯 상세 페이지 2차 정밀 수집 (Timeout 방어 로직 포함)
                        try:
                            det_res = requests.get(config['det_url'], params=p_det, headers=HEADERS, timeout=5).json()
                            det_data = det_res.get('response', {}).get('body', {}).get('item', {})
                            if isinstance(det_data, dict):
                                area = det_data.get('areaLmttList') or "제한없음"
                                combined_g2b = det_data.get('g2bPblancNo') or p_no
                                budget = det_data.get('budgetAmount') or it.get('asignBdgtAmt') or 0
                        except: pass

                        status = it.get('progrsSttus') or "진행중"
                        if ("진행중" in status or status == "") and any(t in area for t in TARGET_AREAS):
                            total_results.append({
                                '구분': config['type'],
                                '통합참조번호': combined_g2b,
                                '공고명': bid_nm,
                                '수요기관': it.get('ornt'),
                                '지역제한': area,
                                '예산(원)': int(pd.to_numeric(budget, errors='coerce') or 0),
                                '마감일시': format_d2b_date(it.get(config['clos']))
                            })
        except Exception as e:
            st.error(f"🚨 {config['type']} 서버 접속 중 오류: {e}")

    # --- [3] 결과 출력 ---
    status_msg.empty()
    if total_results:
        df = pd.DataFrame(total_results).drop_duplicates(subset=['통합참조번호']).sort_values(by='마감일시')
        st.success(f"✅ 국방부 수색 완료! 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df.style.format({'예산(원)': '{:,}원'}), use_container_width=True)
        
        # 엑셀 다운로드
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='D2B_REFINED')
        st.download_button(label="📥 국방부 단독 리포트 다운로드", data=output.getvalue(), file_name=f"D2B_ONLY_{now.strftime('%m%d')}.xlsx")
    else:
        st.warning("⚠️ 현재 조건에 맞는 국방부 공고가 없습니다. 서버 점검 여부를 확인하세요.")
