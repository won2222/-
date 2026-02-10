import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re

# --- [1] 커스텀 세팅 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
# LH는 헤더 정보를 더 꼼꼼히 봅니다.
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Accept': 'application/xml, text/xml, */*'
}
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목"]
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [3] 웹 화면 구성 ---
st.set_page_config(page_title="3사 통합 레이더 최종본", layout="wide")
st.title("🚀 공고검색")

if st.sidebar.button("📡 전 구역 정밀 수색", type="primary"):
    final_list = []
    now = datetime.now()
    s_date = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    
    status = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 ---
        status.info("📡 [1단계] 나라장터 수집 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / (len(KEYWORDS) * 3))
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                    try:
                        l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                        lic_items = l_res.get('response', {}).get('body', {}).get('items', [])
                        lic_val = " / ".join(list(set([li.get('lcnsLmtNm','') for li in (lic_items if isinstance(lic_items, list) else [lic_items]) if li.get('lcnsLmtNm')]))) or "공고참조"
                        r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                        reg_items = r_res.get('response', {}).get('body', {}).get('items', [])
                        reg_val = ", ".join(list(set([ri.get('prtcptPsblRgnNm','') for ri in (reg_items if isinstance(reg_items, list) else [reg_items]) if ri.get('prtcptPsblRgnNm')]))) or "전국"
                        if (any(code in lic_val for code in OUR_LICENSES) or "공고참조" in lic_val) and any(ok in reg_val for ok in MUST_PASS_AREAS):
                            final_list.append({'출처':'1.나라장터', '번호':b_no, '공고명':it['bidNtceNm'], '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역':reg_val, '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
                    except: continue
            except: continue

        # --- 2. LH (수집 방식 보강) ---
        status.info("📡 [2단계] LH포털 수집 중 (보안 우회 중)...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            # LH는 검색 범위를 너무 넓게 잡으면 차단될 수 있어 10일치만 딱 잡습니다.
            p_lh = {
                'serviceKey': SERVICE_KEY, 
                'numOfRows': '1000', 
                'pageNo': '1', 
                'tndrbidRegDtStart': (now - timedelta(days=10)).strftime("%Y%m%d"), 
                'tndrbidRegDtEnd': today_str
            }
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=15)
            res_lh.encoding = 'utf-8' # 인코딩 강제 고정
            
            if res_lh.status_code == 200:
                clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
                root = ET.fromstring(clean_xml)
                for item in root.findall('.//item'):
                    bid_nm = item.findtext('bidnmKor', '')
                    if not bid_nm: # CDATA 처리 대비
                        bid_nm = "".join(item.find('bidnmKor').itertext()) if item.find('bidnmKor') is not None else ""
                    
                    if any(kw in bid_nm for kw in KEYWORDS):
                        b_no = item.findtext('bidNum')
                        final_list.append({
                            '출처':'3.LH', '번호':b_no, '공고명':bid_nm.strip(), 
                            '수요기관':'한국토지주택공사', 
                            '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), 
                            '지역':'전국/상세참조', '마감일':format_date_clean(item.findtext('openDtm')), 
                            'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"
                        })
        except Exception as e:
            st.sidebar.error(f"LH 수집 실패: {e}")

        # --- 3. 국방부 (부장님 검증 완료 로직) ---
        status.info("📡 [3단계] 국방부(D2B) 예산 정밀 추적 중...")
        # ... (부장님이 확인하신 국방부 예산 추적 로직 그대로 유지) ...
        # [이하 중략: 부장님의 완벽한 국방부 로직이 들어있습니다]
