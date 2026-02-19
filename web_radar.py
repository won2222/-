import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import time

# --- [1] 부장님 정예 설정 (면허 필터 추가) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

G2B_KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
                "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
CORE_KEYWORDS = ["폐기물", "폐목재", "식물성", "낙엽", "임목", "가연성", "폐가구", "초본류", "부유물"]

# 🎯 면허 및 지역 필터 조건
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS = ['경기', '평택', '화성', '전국', '제한없음', '서울', '인천'] 
EXCLUDE_LIST = ['충청', '전라', '강원', '경상', '제주', '부산', '대구', '광주', '대전', '울산', '세종', '충북', '충남', '경북', '경남', '전북', '전남']

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] UI 레이아웃 ---
st.set_page_config(page_title="THE RADAR v1450", layout="wide")
st.title("📡 THE RADAR v1450.0")
st.caption("v169.0 기반 - 나라장터 면허 필터 & 국방부 지역 정보 보강")
st.divider()

st.sidebar.header("🕹️ 수집 컨트롤")
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
        # --- 🎯 1. 나라장터 (G2B) - 면허 및 지역 정밀 필터 ---
        status_st.info("📡 [1/3] 나라장터 수색 및 면허·지역 검증 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        g_raw = []
        for i, kw in enumerate(G2B_KEYWORDS):
            prog_bar.progress((i + 1) / (len(G2B_KEYWORDS) * 3))
            try:
                time.sleep(0.1)
                params = {'serviceKey': SERVICE_KEY, 'numOfRows': '50', 'type': 'json', 'inqryDiv': '1', 
                          'inqryBgnDt': s_date_api+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=params, timeout=10).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                for it in ([items] if isinstance(items, dict) else items):
                    it['searchKeyword'] = kw
                    g_raw.append(it)
            except: continue
        
        if g_raw:
            df_g = pd.DataFrame(g_raw).drop_duplicates(subset=['bidNtceNo'])
            for idx, row in df_g.iterrows():
                b_no, b_ord = row['bidNtceNo'], str(row.get('bidNtceOrd', '00')).zfill(2)
                reg_val, lic_val, is_pass = "제한없음", "공고참조", True
                
                try:
                    # 🎯 지역 필터 (v169 베이스)
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', 
                                         params={'ServiceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=3).json()
                    regs = [str(ri.get('prtcptPsblRgnNm', '')) for ri in r_res.get('response', {}).get('body', {}).get('items', [])]
                    reg_val = ", ".join(list(set(regs))) if regs else "제한없음"
                    
                    # 🎯 면허 필터 추가 (v169 베이스)
                    l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', 
                                         params={'ServiceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=3).json()
                    lics = [str(li.get('lcnsLmtNm', '')) for li in l_res.get('response', {}).get('body', {}).get('items', [])]
                    lic_val = ", ".join(list(set(lics))) if lics else "공고참조"

                    # 🎯 필터링 판정: 면허 매칭 확인
                    lic_ok = any(code in lic_val for code in OUR_LICENSES) or lic_val == "공고참조"
                    reg_ok = any(ok in reg_val for ok in MUST_PASS)
                    
                    if lic_ok and reg_ok:
                        if any(no in reg_val for no in EXCLUDE_LIST) and not any(must in reg_val for must in ['경기', '평택', '화성']):
                            is_pass = False
                        else: is_pass = True
                    else: is_pass = False
                except: pass

                if is_pass:
                    final_list.append({'출처': '1.나라장터', '키워드': row['searchKeyword'], '번호': b_no, '공고명': row['bidNtceNm'], '기관': row['dminsttNm'], '예산': int(pd.to_numeric(row.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역': reg_val, '마감일시': clean_date_strict(row.get('bidClseDt')), 'URL': row.get('bidNtceDtlUrl', '')})

        # --- 🎯 2. LH (e-Bid) ---
        status_st.info("📡 [2/3] LH 수색 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            res_lh = requests.get(url_lh, params={'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 'tndrbidRegDtStart': s_date_api, 'tndrbidRegDtEnd': today_api, 'cstrtnJobGb': '1'}, timeout=15)
            res_lh.encoding = res_lh.apparent_encoding
            root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text))
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in CORE_KEYWORDS):
                    b_no = item.findtext('bidNum')
                    final_list.append({'출처': '2.LH', '키워드': 'LH검색', '번호': b_no, '공고명': bid_nm, '기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt'), errors='coerce') or 0), '지역': '전국/공고참조', '마감일시': clean_date_strict(item.findtext('openDtm')), 'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}"})
        except: pass
        prog_bar.progress(0.66)

        # --- 🎯 3. 국방부 (D2B) - 지역 정보 보강 ---
        status_st.info("📡 [3/3] 국방부 지역 및 예산 정밀 추적 중...")
        try:
            for bt in ['bid', 'priv']:
                url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
                res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, timeout=15).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')
                    if any(kw in bid_nm for kw in CORE_KEYWORDS) and (bt=='priv' or (today_api <= str(clos_dt)[:8] <= target_end_day)):
                        budget, area = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0, "상세확인"
                        url_det = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancDetail' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanDetail'}"
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'), 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if bt == 'priv': p_det.update({'iemNo': it.get('iemNo'), 'ntatPlanDate': it.get('ntatPlanDate')})
                        try:
                            det_res = requests.get(url_det, params=p_det, timeout=5).json()
                            det_item = det_res.get('response', {}).get('body', {}).get('item', {})
                            budget = det_item.get('budgetAmount') or budget
                            # 🎯 국방부 상세 지역 정보 추출
                            area = det_item.get('areaLmttList') or area
                        except: pass
                        
                        # 🎯 국방부 지역 필터 적용
                        if any(must in area for must in MUST_PASS):
                            final_list.append({'출처': '3.국방부', '키워드': '국방검색', '번호': it.get('pblancNo') or it.get('dcsNo'), '공고명': bid_nm, '기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': area, '마감일시': clean_date_strict(clos_dt), 'URL': 'https://www.d2b.go.kr'})
        except: pass
        prog_bar.progress(1.0)

        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일시'])
            st.success(f"✅ 작전 완료! {len(df)}건 확보.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 전략 리포트 저장", data=output.getvalue(), file_name=f"RADAR_v1450_{today_api}.xlsx")
        else:
            st.warning("⚠️ 포착된 공고가 없습니다.")
    except Exception as e:
        st.error(f"🚨 오류 발생: {e}")
