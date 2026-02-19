import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re

# --- [1] 설정 및 유틸리티 ---
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
st.set_page_config(page_title="THE RADAR v670", layout="wide")
st.title("📡 THE RADAR v670.0")
st.caption("데이터 파싱 정밀 보정 및 LH 직통 엔진")

# --- [3] 사이드바 설정 ---
st.sidebar.header("🕹️ 수색 설정")
s_date = st.sidebar.date_input("수색 시작일", datetime.now() - timedelta(days=14))
e_date = st.sidebar.date_input("수색 종료일", datetime.now() + timedelta(days=7))

user_kw = st.sidebar.text_area("필터 키워드", "폐기물, 운반, 폐목재, 임목, 나무, 벌채, 뿌리, 재활용", height=100)
kw_list = [k.strip() for k in user_kw.split(",") if k.strip()]

OUR_LICENSES = ['1226', '1227', '6786', '6770']
# '경기'만 있어도 통과되도록 필터링
MUST_PASS_AREAS = ['경기', '평택', '화성', '서울', '인천', '전국', '제한없음']

if st.sidebar.button("🚀 정밀 수색 개시", type="primary"):
    final_list = []
    s_str = s_date.strftime("%Y%m%d")
    e_str = e_date.strftime("%Y%m%d")
    today_str = datetime.now().strftime("%Y%m%d")
    
    status = st.empty()
    
    # --- 1. LH (부장님 성공 로직 100% 동기화) ---
    status.info(f"📡 LH 수색 중... ({s_str} ~ {e_str})")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 
                'tndrbidRegDtStart': s_str, 'tndrbidRegDtEnd': e_str, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=25)
        res_lh.encoding = res_lh.apparent_encoding # 🎯 성공 포인트
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        
        if "<resultCode>00</resultCode>" in clean_xml:
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

    # --- 2. 나라장터 (구조적 파싱 보정) ---
    status.info("📡 나라장터 면허/지역 정밀 대조 중...")
    url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
    for kw in kw_list:
        try:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 
                 'inqryBgnDt': s_str+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                
                # 🎯 나라장터 면허/지역 필터 보정
                l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                lic_data = l_res.get('response', {}).get('body', {}).get('items', [])
                lic_names = [ld.get('lcnsLmtNm', '') for ld in (lic_data if isinstance(lic_data, list) else [lic_data])]
                
                r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                reg_data = r_res.get('response', {}).get('body', {}).get('items', [])
                reg_names = [rd.get('prtcptPsblRgnNm', '') for rd in (reg_data if isinstance(reg_data, list) else [reg_data])]
                
                # 면허나 지역이 없으면(전국) 통과, 있으면 부장님 리스트와 대조
                lic_ok = not lic_names or any(any(code in name for code in OUR_LICENSES) for name in lic_names)
                reg_ok = not reg_names or any(any(area in name for area in MUST_PASS_AREAS) for name in reg_names)

                if lic_ok and reg_ok:
                    final_list.append({
                        '출처': 'G2B', '번호': b_no, '공고명': it['bidNtceNm'], '수요기관': it['dminsttNm'],
                        '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역': ", ".join(reg_names) or "전국",
                        '마감일': date_fmt(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')
                    })
        except: continue

    # --- [결과 출력] ---
    status.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
        st.success(f"✅ 수색 완료! 총 {len(df)}건 확보.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
    else:
        st.warning("⚠️ 포착된 공고가 없습니다. 날짜를 조정해 보세요.")
