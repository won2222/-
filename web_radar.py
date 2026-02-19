import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import time

# --- [1] 부장님 정예 설정 (v169.0 로직 기반) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 🎯 나라장터 전용 키워드 (18종 풀세트)
G2B_KEYWORDS = [
    "폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
    "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"
]

# 🎯 LH/국방부 등 기타 기관 전용 키워드 (핵심 9종)
CORE_KEYWORDS = ["폐기물", "폐목재", "식물성", "낙엽", "임목", "가연성", "폐가구", "초본류", "부유물"]

# 🎯 MUST PASS 지역 (부장님 오더)
MUST_PASS = ['경기', '경기도', '평택', '평택시', '화성', '화성시', '전국', '제한없음']

# 🎯 EXCLUDE 지역 (배제 리스트 - 서울/인천 삭제 완료)
EXCLUDE_LIST = ['충청', '전라', '강원', '경상', '제주', '부산', '대구', '광주', '대전', '울산', '세종', '충북', '충남', '경북', '경남', '전북', '전남']

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v169", layout="wide")
st.title("📡 THE RADAR v1350.0")
st.caption("v169.0 정예 로직 - 서울/인천 배제 해제 및 경기권 집중 타격")
st.divider()

# --- [3] 사이드바 설정 ---
st.sidebar.header("🕹️ 수집 엔진 컨트롤")
days_range = st.sidebar.slider("수색 범위 (일)", 1, 14, 4)

if st.sidebar.button("🚀 정밀 타겟 수색 개시", type="primary"):
    final_list = []
    now = datetime.now()
    s_date_api = (now - timedelta(days=days_range)).strftime("%Y%m%d")
    today_api = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=days_range)).strftime("%Y%m%d")
    
    status_st = st.empty()
    prog_bar = st.progress(0)
    
    try:
        # --- 🎯 1. 나라장터 (G2B) - 18종 키워드 수집 ---
        status_st.info("📡 [1/3] 나라장터(G2B) 18종 키워드 수색 및 필터링 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        g_raw = []
        for i, kw in enumerate(G2B_KEYWORDS):
            prog_bar.progress((i + 1) / (len(G2B_KEYWORDS) * 3))
            params = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 
                      'inqryBgnDt': s_date_api+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
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
                b_no, b_ord = row['bidNtceNo'], str(row.get('bidNtceOrd', '00')).zfill(2)
                reg_val, is_pass = "제한없음", True
                
                try:
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', 
                                         params={'ServiceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                    regs = [str(ri.get('prtcptPsblRgnNm', '')) for ri in r_res.get('response', {}).get('body', {}).get('items', [])]
                    reg_val = ", ".join(list(set(regs))) if regs else "제한없음"
                    
                    # 🎯 부장님 필터 로직 보정
                    # 1. MUST_PASS (경기 등)가 포함되어 있으면 우선 통과
                    if any(ok in reg_val for ok in MUST_PASS):
                        is_pass = True
                    # 2. MUST_PASS가 없고 배제 리스트에만 걸리면 탈락
                    elif any(no in reg_val for no in EXCLUDE_LIST):
                        is_pass = False
                except: reg_val = "공고참조"

                if is_pass:
                    final_list.append({
                        '출처': '1.나라장터', '키워드': row['searchKeyword'], '번호': b_no, '공고명': row['bidNtceNm'], 
                        '기관': row['dminsttNm'], '예산': int(pd.to_numeric(row.get('asignBdgtAmt', 0), errors='coerce') or 0),
                        '지역': reg_val, '마감일시': clean_date_strict(row.get('bidClseDt')), 'URL': row.get('bidNtceDtlUrl', '')
                    })

        # --- 🎯 2. LH (e-Bid) - 핵심 키워드 수집 ---
        status_st.info("📡 [2/3] LH포털 수색 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            res_lh = requests.get(url_lh, params={'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 
                                                  'tndrbidRegDtStart': s_date_api, 'tndrbidRegDtEnd': today_api, 'cstrtnJobGb': '1'}, timeout=10)
            res_lh.encoding = res_lh.apparent_encoding
            root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text))
            lh_items = root.findall('.//item')
            for item in lh_items:
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in CORE_KEYWORDS):
                    b_no = item.findtext('bidNum')
                    final_list.append({
                        '출처': '2.LH', '키워드': 'LH검색', '번호': b_no, '공고명': bid_nm, 
                        '기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt'), errors='coerce') or 0),
                        '지역': '전국/공고참조', '마감일시': clean_date_strict(item.findtext('openDtm')), 
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}"
                    })
        except: pass
        prog_bar.progress(0.66)

        # --- 🎯 3. 국방부 (D2B) - 핵심 키워드 수집 ---
        status_st.info("📡 [3/3] 방위사업청(D2B) 예산 정밀 수색 중...")
        try:
            for bt in ['bid', 'priv']:
                url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
                res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, timeout=10).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')
                    if any(kw in bid_nm for kw in CORE_KEYWORDS) and (bt=='priv' or (today_api <= str(clos_dt)[:8] <= target_end_day)):
                        budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                        url_det = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancDetail' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanDetail'}"
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'), 
                                 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if bt == 'priv': p_det.update({'iemNo': it.get('iemNo'), 'ntatPlanDate': it.get('ntatPlanDate')})
                        try:
                            det_res = requests.get(url_det, params=p_det, timeout=5).json()
                            det_item = det_res.get('response', {}).get('body', {}).get('item', {})
                            budget = det_item.get('budgetAmount') or budget
                        except: pass

                        final_list.append({
                            '출처': '3.국방부', '키워드': '국방검색', '번호': it.get('pblancNo') or it.get('dcsNo'), 
                            '공고명': bid_nm, '기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0),
                            '지역': '상세확인', '마감일시': clean_date_strict(clos_dt), 'URL': 'https://www.d2b.go.kr'
                        })
        except: pass
        prog_bar.progress(1.0)

        # --- [최종 결과] ---
        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일시'])
            st.success(f"✅ 수색 완료! 서울·인천을 포함한 경기권 타겟 공고 {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 전략 리포트(Excel) 저장", data=output.getvalue(), file_name=f"RADAR_v1350_{today_api}.xlsx")
        else:
            st.warning("⚠️ 검색된 공고가 없습니다.")

    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
