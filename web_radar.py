import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re

# --- [1] 기본 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def lh_cleaner(text):
    if not text: return ""
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

def date_fmt(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] UI 레이아웃 ---
st.set_page_config(page_title="THE RADAR v750", layout="wide")
st.title("📡 THE RADAR v750.0")
st.info("LH는 입력된 날짜로, 나라장터/국방부는 자동 설정된 최신 기간으로 수색합니다.")

# --- [3] 사이드바 설정 (부장님 커스텀) ---
st.sidebar.header("🕹️ LH 전용 날짜 설정")
# LH는 부장님이 직접 제어
lh_s_date = st.sidebar.date_input("LH 수색 시작일", datetime.now() - timedelta(days=14))
lh_e_date = st.sidebar.date_input("LH 수색 종료일", datetime.now() + timedelta(days=7))

st.sidebar.divider()
st.sidebar.header("🔑 공통 필터 키워드")
user_kw = st.sidebar.text_area("키워드 (쉼표 구분)", "폐기물, 운반, 폐목재, 임목, 나무, 벌채, 뿌리, 재활용, 잔재물", height=120)
kw_list = [k.strip() for k in user_kw.split(",") if k.strip()]

# 베이스 필터 조건
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기', '평택', '화성', '서울', '인천', '전국', '제한없음']

if st.sidebar.button("🚀 전 구역 정밀 수색 개시", type="primary"):
    final_list = []
    
    # 🎯 LH용 날짜 (입력값)
    lh_s = lh_s_date.strftime("%Y%m%d")
    lh_e = lh_e_date.strftime("%Y%m%d")
    
    # 🎯 나라장터/국방부 자동 날짜 설정
    today = datetime.now()
    g2b_s = (today - timedelta(days=7)).strftime("%Y%m%d") # 나라장터: 공고일 기준 일주일 전부터
    g2b_e = today.strftime("%Y%m%d")
    d2b_e_limit = (today + timedelta(days=7)).strftime("%Y%m%d") # 국방부: 마감일 기준 일주일 후까지
    
    status = st.empty()
    prog = st.progress(0)

    # --- 1. LH (부장님 성공 로직 - 날짜 직공) ---
    status.info(f"📡 LH 수색 중... ({lh_s} ~ {lh_e})")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': lh_s, 'tndrbidRegDtEnd': lh_e, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        res_lh.encoding = res_lh.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        for item in root.findall('.//item'):
            bid_nm = lh_cleaner(item.findtext('bidnmKor', ''))
            if any(kw in bid_nm for kw in kw_list):
                final_list.append({
                    '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm,
                    '수요기관': 'LH공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                    '지역': '전국', '마감일': date_fmt(item.findtext('openDtm')),
                    'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                })
    except: pass
    prog.progress(33)

    # --- 2. 나라장터 (자동 기간: 공고일 기준 최근 7일) ---
    status.info(f"📡 나라장터 수색 중... ({g2b_s} ~ {g2b_e})")
    url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
    # 부하를 줄이기 위해 상위 키워드 위주로 수색
    for kw in kw_list:
        try:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '50', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': g2b_s+'0000', 'inqryEndDt': g2b_e+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                # 면허/지역 2차 필터링
                r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=3).json()
                reg_data = r_res.get('response', {}).get('body', {}).get('items', [])
                reg_names = [rd.get('prtcptPsblRgnNm', '') for rd in (reg_data if isinstance(reg_data, list) else [reg_data])]
                
                if not reg_names or any(any(area in name for area in MUST_PASS_AREAS) for name in reg_names):
                    final_list.append({
                        '출처': 'G2B', '번호': b_no, '공고명': it.get('bidNtceNm'), '수요기관': it.get('dminsttNm'),
                        '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역': ", ".join(reg_names) or "전국",
                        '마감일': date_fmt(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')
                    })
        except: continue
    prog.progress(66)

    # --- 3. 국방부 (자동 기간: 오늘 ~ 마감 7일 후까지) ---
    status.info(f"📡 국방부 수색 중... (~ {d2b_e_limit})")
    try:
        # 국방부는 수의계약 위주로 기간 필터 적용
        p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json', 'prqudoPresentnClosDateBegin': g2b_e, 'prqudoPresentnClosDateEnd': d2b_e_limit}
        res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList", params=p_d, timeout=10).json()
        items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        for it in ([items_d] if isinstance(items_d, dict) else items_d):
            bid_nm = it.get('othbcNtatNm', '')
            if any(kw in bid_nm for kw in kw_list):
                final_list.append({
                    '출처': 'D2B(수의)', '번호': it.get('dcsNo'), '공고명': bid_nm, '수요기관': it.get('ornt'),
                    '예산': int(pd.to_numeric(it.get('budgetAmount', 0))), '지역': '상세참조',
                    '마감일': date_fmt(it.get('prqudoPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'
                })
    except: pass
    prog.progress(100)

    # --- [최종 결과] ---
    status.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
        st.success(f"✅ 수색 완료! 총 {len(df)}건 확보.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
    else:
        st.warning("⚠️ 포착된 공고가 없습니다. 키워드나 LH 날짜를 확인해 보세요.")
