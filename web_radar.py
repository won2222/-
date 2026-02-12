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
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 정예 키워드 및 필터 조건
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR", layout="wide")
st.title("📡 THE RADAR")
st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE - 7-DAY DEADLINE FOCUS")
st.divider()

# 수색 기간 정보 실시간 표시
KST = pytz.timezone('Asia/Seoul')
now = datetime.now(KST)
future_7_dt = now + timedelta(days=7)
future_7_str = future_7_dt.strftime("%Y%m%d")

st.sidebar.subheader("📅 국방부 수색 타겟")
st.sidebar.warning(f"**마감일 기준**\n오늘 ~ {future_7_dt.strftime('%m-%d')} 마감분\n(딱 1주일치만 포착)")

if st.sidebar.button("🔍 1주일 마감분 정밀 수색", type="primary"):
    final_list = []
    
    # 날짜 파라미터 세팅
    s_date_past = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    future_7_limit = future_7_str  # 딱 7일 뒤
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 (최근 7일 공고) ---
        status_st.info("📡 [1/2] 나라장터/외 유관기관 수색 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / 30)
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date_past+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
            try:
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    if "전자입찰" not in it.get('bidMethdNm', ''): continue
                    final_list.append({'출처':'G2B', '번호':it.get('bidNtceNo'), '공고명':it['bidNtceNm'], '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역':'전국', '마감일':format_date_clean(it.get('bidClseDt')), '마감일자_비교': str(it.get('bidClseDt'))[:8]})
            except: continue

        # --- 2. 국방부 (부장님 요청: 정확히 1주일 이내 마감건) ---
        status_st.info(f"📡 [2/2] 국방부 정밀 컷오프 수색 중 (~ {future_7_dt.strftime('%m-%d')})")
        d2b_configs = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail', 'c': 'biddocPresentnClosDt'}, 
                      {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail', 'c': 'prqudoPresentnClosDt'}]
        
        for cfg in d2b_configs:
            p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
            if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': today_str, 'prqudoPresentnClosDateEnd': future_7_limit})
            
            try:
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, timeout=10).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt_raw = str(it.get(cfg['c'], ''))[:8]
                    
                    # 🎯 핵심: 7일 이내 마감건만 엄격하게 필터링
                    if any(kw in bid_nm for kw in KEYWORDS):
                        if today_str <= clos_dt_raw <= future_7_limit:
                            p_no, d_year, d_no = str(it.get('pblancNo', '')), str(it.get('demandYear', '')), str(it.get('dcsNo', ''))
                            p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': p_no, 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': d_year, 'orntCode': it.get('orntCode'), 'dcsNo': d_no, '_type': 'json'}
                            if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                            
                            area, budget = "국방부상세", 0
                            try:
                                det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                                if det:
                                    area = det.get('areaLmttList') or area
                                    budget = det.get('budgetAmount') or it.get('asignBdgtAmt') or 0
                                    p_no = det.get('g2bPblancNo') or p_no
                            except: pass
                            
                            if any(t in area for t in MUST_PASS_AREAS):
                                final_list.append({'출처': f"D2B({cfg['t']})", '번호': p_no, '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': area, '마감일': format_date_clean(it.get(cfg['c'])), '마감일자_비교': clos_dt_raw})
            except: continue

        # --- [최종 출력] ---
        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일자_비교'])
            st.success(f"✅ 수색 완료! 딱 1주일 내 마감 건 포함 총 {len(df)}건 확보.")
            st.dataframe(df.drop(columns=['마감일자_비교']).style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.drop(columns=['마감일자_비교']).to_excel(writer, index=False, sheet_name='RADAR_REPORT')
            st.download_button(label="📥 전략 리포트(Excel) 다운로드", data=output.getvalue(), file_name=f"RADAR_7days_{today_str}.xlsx")
        else:
            st.warning("⚠️ 1주일 이내 마감되는 국방부 공고나 최근 7일 내 신규 공고가 없습니다.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
