import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import time

# --- [1] 부장님 v169.0 기반 핵심 수집 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 수집 대상 키워드 (부장님 오더 18종)
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
            "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v169", layout="wide")
st.title("📡 THE RADAR v169.0")
st.caption("G2B / LH / D2B 서버 실시간 수집 엔진 (작전 상황실)")
st.divider()

# --- [3] 사이드바 컨트롤러 (수집 기간 설정) ---
st.sidebar.header("🕹️ 수집 엔진 컨트롤")
days_range = st.sidebar.slider("수색 범위 (기준일로부터 과거/미래)", 1, 14, 4)

if st.sidebar.button("🚀 전 구역 수집 개시", type="primary"):
    final_list = []
    now = datetime.now()
    
    # v169.0 API 검색용 날짜 로직
    s_date_api = (now - timedelta(days=days_range)).strftime("%Y%m%d")
    today_api = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=days_range)).strftime("%Y%m%d")
    
    status_st = st.empty()
    prog_bar = st.progress(0)
    
    try:
        # --- 🎯 1. 나라장터 (G2B) 수집 엔진 ---
        status_st.info("📡 [1/3] 나라장터(G2B) 서버 접속 및 키워드 순회 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        g_raw = []
        for i, kw in enumerate(KEYWORDS):
            # 대시보드 진도율 표시
            prog_bar.progress((i + 1) / (len(KEYWORDS) * 3))
            params = {
                'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 
                'inqryDiv': '1', 'inqryBgnDt': s_date_api+'0000', 
                'inqryEndDt': today_api+'2359', 'bidNtceNm': kw
            }
            try:
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=params, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                for it in ([items] if isinstance(items, dict) else items):
                    it['searchKeyword'] = kw
                    g_raw.append(it)
            except: pass
        
        if g_raw:
            df_g = pd.DataFrame(g_raw).drop_duplicates(subset=['bidNtceNo'])
            for idx, row in df_g.iterrows():
                final_list.append({
                    '출처': '1.나라장터', '키워드': row['searchKeyword'], '번호': row['bidNtceNo'], 
                    '공고명': row['bidNtceNm'], '기관': row['dminsttNm'], 
                    '예산': int(pd.to_numeric(row.get('asignBdgtAmt', 0), errors='coerce') or 0),
                    '마감일시': clean_date_strict(row.get('bidClseDt')), 'URL': row.get('bidNtceDtlUrl', '')
                })

        # --- 🎯 2. LH (e-Bid) 수집 엔진 (XML 파싱) ---
        status_st.info("📡 [2/3] LH포털 서버 접속 및 XML 데이터 세척 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            params_lh = {
                'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 
                'tndrbidRegDtStart': s_date_api, 'tndrbidRegDtEnd': today_api, 'cstrtnJobGb': '1'
            }
            res_lh = requests.get(url_lh, params=params_lh, timeout=10)
            res_lh.encoding = res_lh.apparent_encoding
            # XML 선언부 제거 및 파싱 (v169 로직)
            root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text))
            lh_items = root.findall('.//item')
            for item in lh_items:
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    b_no = item.findtext('bidNum')
                    final_list.append({
                        '출처': '2.LH', '키워드': 'LH검색', '번호': b_no, '공고명': bid_nm, 
                        '기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt'), errors='coerce') or 0),
                        '마감일시': clean_date_strict(item.findtext('openDtm')), 
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}"
                    })
        except: pass
        prog_bar.progress(0.66)

        # --- 🎯 3. 방위사업청 (D2B) 수집 엔진 (상세 재조회 포함) ---
        status_st.info("📡 [3/3] 방위사업청(D2B) 서버 접속 및 예산 정밀 추적 중...")
        try:
            # 일반입찰(bid) 및 수의계약(priv) 순회 수집
            for bt in ['bid', 'priv']:
                url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
                res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, timeout=10).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')
                    
                    # 수집 범위 내 공고만 선별
                    if any(kw in bid_nm for kw in KEYWORDS) and (bt=='priv' or (today_api <= str(clos_dt)[:8] <= target_end_day)):
                        # 🎯 v169 핵심: 상세 페이지 재접속을 통한 예산(budgetAmount) 보정
                        budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                        url_det = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancDetail' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanDetail'}"
                        p_det = {
                            'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'), 
                            'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'
                        }
                        if bt == 'priv': p_det.update({'iemNo': it.get('iemNo'), 'ntatPlanDate': it.get('ntatPlanDate')})
                        try:
                            det_res = requests.get(url_det, params=p_det, timeout=5).json()
                            det_item = det_res.get('response', {}).get('body', {}).get('item', {})
                            budget = det_item.get('budgetAmount') or budget
                        except: pass

                        final_list.append({
                            '출처': '3.국방부', '키워드': '국방검색', '번호': it.get('pblancNo') or it.get('dcsNo'), 
                            '공고명': bid_nm, '기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0),
                            '마감일시': clean_date_strict(clos_dt), 'URL': 'https://www.d2b.go.kr'
                        })
        except: pass
        prog_bar.progress(1.0)

        # --- [4] 수집 결과 대시보드 출력 ---
        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일시'])
            st.success(f"✅ 작전 성공! 총 {len(df)}건의 최신 공고를 확보했습니다.")
            
            # 메트릭 표시
            c1, c2, c3 = st.columns(3)
            c1.metric("G2B 수집", f"{len(df[df['출처']=='1.나라장터'])}건")
            c2.metric("LH 수집", f"{len(df[df['출처']=='2.LH'])}건")
            c3.metric("D2B 수집", f"{len(df[df['출처']=='3.국방부'])}건")
            
            # 데이터 테이블
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            # 엑셀 다운로드 (부장님 리포트 서식 유지)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='통합수집공고')
            st.download_button(label="📥 통합 리포트(Excel) 다운로드", data=output.getvalue(), file_name=f"RADAR_REPORT_{today_api}.xlsx")
        else:
            st.warning("⚠️ 현재 수집 범위 내에 검색된 공고가 없습니다.")

    except Exception as e:
        st.error(f"🚨 수집 엔진 오류 발생: {e}")
