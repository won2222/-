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

# --- [1] 부장님 정예 설정 및 클리닝 엔진 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def lh_cleaner(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>', '', text)
    return text.strip()

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] UI 레이아웃 ---
st.set_page_config(page_title="THE RADAR v1050", layout="wide")
st.title("📡 THE RADAR v1050.0")
st.caption("나라장터 구조적 파싱 & 국방부 정밀 필터링 보강")

# --- [3] 사이드바 컨트롤러 ---
st.sidebar.header("🕹️ LH 수색 기간 (직통)")
lh_s_date = st.sidebar.date_input("LH 시작일", datetime.now() - timedelta(days=14))
lh_e_date = st.sidebar.date_input("LH 종료일", datetime.now() + timedelta(days=7))

# 부장님 지정 키워드 셋팅
G2B_KW = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
CORE_KW = ["폐목재", "폐가구", "임목", "폐기물", "낙엽"]

# 타겟 지역 (경기/평택/화성 등 부장님 핵심 지역)
MUST_PASS_AREAS = ['경기', '평택', '화성', '서울', '인천', '전국', '제한없음']

if st.sidebar.button("🚀 정밀 필터링 수색 개시", type="primary"):
    final_list = []
    now = datetime.now(pytz.timezone('Asia/Seoul'))
    
    # 날짜 셋팅
    lh_s, lh_e = lh_s_date.strftime("%Y%m%d"), lh_e_date.strftime("%Y%m%d")
    g2b_s = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    d2b_future = (now + timedelta(days=7)).strftime("%Y%m%d")

    status_st = st.empty()
    prog = st.progress(0)

    # --- 🎯 PHASE 1. LH (성공 로직 유지) ---
    status_st.info("📡 LH 직통 엔진 가동 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': lh_s, 'tndrbidRegDtEnd': lh_e, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=20)
        res_lh.encoding = res_lh.apparent_encoding
        root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text).strip())
        for item in root.findall('.//item'):
            bid_nm = lh_cleaner(item.findtext('bidnmKor', ''))
            if any(kw in bid_nm for kw in CORE_KW):
                final_list.append({'출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm, '수요기관': 'LH공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), '지역': '전국', '마감일': format_date_clean(item.findtext('openDtm')), 'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"})
    except: pass
    prog.progress(33)

    # --- 🎯 PHASE 2. 나라장터 (구조 분해 필터 복구) ---
    status_st.info("📡 나라장터 18종 키워드 및 지역 정밀 필터링 중...")
    url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
    for kw in G2B_KW:
        try:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': g2b_s+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                
                # 지역 제한 상세 파싱
                r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                reg_items = r_res.get('response', {}).get('body', {}).get('items', [])
                reg_names = [rd.get('prtcptPsblRgnNm', '') for rd in (reg_items if isinstance(reg_items, list) else [reg_items])]
                
                # 부장님 베이스: 타겟 지역 포함 여부 엄격 대조
                if not reg_names or any(any(ar in name for ar in MUST_PASS_AREAS) for name in reg_names):
                    final_list.append({'출처': 'G2B', '번호': b_no, '공고명': it.get('bidNtceNm'), '수요기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역': ", ".join(reg_names) or "전국", '마감일': format_date_clean(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')})
        except: continue
    prog.progress(66)

    # --- 🎯 PHASE 3. 국방부 (상세 파싱 필터 강제 적용) ---
    status_st.info("📡 국방부 상세 페이지 예산/지역 필터링 중...")
    d2b_cfg = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail', 'c': 'biddocPresentnClosDt'}, 
               {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail', 'c': 'prqudoPresentnClosDt'}]
    for cfg in d2b_cfg:
        try:
            p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
            if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': today_str, 'prqudoPresentnClosDateEnd': d2b_future})
            res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d).json()
            items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for it in ([items_d] if isinstance(items_d, dict) else items_d):
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                if any(kw in bid_nm for kw in CORE_KW):
                    # 🎯 국방부 핵심: 목록에 있는 예산이 아닌 '상세 API'의 예산과 지역을 다시 체크
                    p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                    if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                    try:
                        det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                        area_limit = str(det.get('areaLmttList', ''))
                        # 상세 데이터에서 지역 필터링 강제 적용
                        if not area_limit or any(ar in area_limit for ar in MUST_PASS_AREAS):
                            final_list.append({'출처': f"D2B({cfg['t']})", '번호': it.get('pblancNo') or it.get('dcsNo'), '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(det.get('budgetAmount') or it.get('asignBdgtAmt') or 0)), '지역': area_limit or "상세확인", '마감일': format_date_clean(it.get(cfg['c'])), 'URL': 'https://www.d2b.go.kr'})
                    except: continue
        except: continue
    prog.progress(100)

    # --- [최종 출력] ---
    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
        st.success(f"✅ 작전 완료! 총 {len(df)}건 확보.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
    else:
        st.warning("⚠️ 포착된 공고가 없습니다. 날짜나 키워드를 조정해 보세요.")
