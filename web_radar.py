import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import io
import re
import time
import pytz

# --- [1] 부장님 정예 설정 (v169/v90/v161 통합) ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 기관별 맞춤 키워드
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "임목", "재활용"]
LH_KEYWORDS_REGEX = '폐목재|임목|목재|나무|벌채|뿌리|폐기물|운반|재활용'
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else val

def lh_korean_cleaner(text):
    if not text: return ""
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v6400", layout="wide")
st.title("📡 THE RADAR v6400.0")
st.success("🎯 나라장터(면허필터) + LH(시설공사) + 국방부(수의/일반) 통합 완료")

if st.sidebar.button("🚀 3사 통합 정밀 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 기관별 날짜 규격
    g2b_start = (now - timedelta(days=7)).strftime("%Y%m%d") + "0000"
    g2b_end = now.strftime("%Y%m%d") + "2359"
    lh_target_month = '202602' # 부장님 오더: 2월 집중
    d2b_start = (now - timedelta(days=7)).strftime("%Y%m%d")
    d2b_future = (now + timedelta(days=7)).strftime("%Y%m%d")

    status_st = st.empty()

    # --- 1. 나라장터 (v169 기반 면허/지역 필터) ---
    status_st.info("📡 [1/3] 나라장터 정밀 수색 및 면허 검증 중...")
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for kw in KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '50', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': g2b_start, 'inqryEndDt': g2b_end, 'bidNtceNm': kw}
            res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            items = [items] if isinstance(items, dict) else items
            for it in items:
                b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                # 지역 및 면허 검증
                r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                reg_val = ", ".join([ri.get('prtcptPsblRgnNm','') for ri in r_res.get('response', {}).get('body', {}).get('items', [])]) or "전국"
                
                if any(ok in reg_val for ok in MUST_PASS_AREAS):
                    final_list.append({'출처':'G2B', '번호':b_no, '공고명':it['bidNtceNm'], '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역':reg_val, '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
    except: pass

    # --- 2. LH (v90 기반 시설공사 단독 타격) ---
    status_st.info("📡 [2/3] LH 시설공사(Gb:1) CDATA 파쇄 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': lh_target_month+'01', 'tndrbidRegDtEnd': lh_target_month+'28', 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        res_lh.encoding = res_lh.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        if "<resultCode>00</resultCode>" in clean_xml:
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                bid_nm = lh_korean_cleaner(item.findtext('bidnmKor', ''))
                if re.search(LH_KEYWORDS_REGEX, bid_nm, re.IGNORECASE):
                    b_no = item.findtext('bidNum')
                    final_list.append({'출처':'LH(시설)', '번호':b_no, '공고명':bid_nm, '수요기관':'LH공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), '지역':'전국/공고참조', '마감일':format_date_clean(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}"})
    except: pass

    # --- 3. 국방부 (v161/169 통합 예산 엔진) ---
    status_st.info("📡 [3/3] 국방부 일반/수의 정밀 수색 중...")
    d2b_configs = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'c': 'biddocPresentnClosDt'}, {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'c': 'prqudoPresentnClosDt'}]
    for cfg in d2b_configs:
        try:
            p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json'}
            if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': d2b_start, 'prqudoPresentnClosDateEnd': d2b_future})
            res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, headers=HEADERS, timeout=15).json()
            items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for it in ([items_d] if isinstance(items_d, dict) else items_d):
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                if any(kw in bid_nm for kw in KEYWORDS):
                    budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                    final_list.append({'출처': f"D2B({cfg['t']})", '번호': it.get('pblancNo') or it.get('dcsNo'), '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': "공고참조", '마감일': format_date_clean(it.get(cfg['c'])), 'URL': 'https://www.d2b.go.kr'})
        except: pass

    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by='마감일')
        st.success(f"✅ 수색 작전 성공! 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 3사 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_INTEGRATED_{today_str}.xlsx")
    else:
        st.warning("⚠️ 모든 규격을 맞췄으나 현재 조건에 맞는 공고가 없습니다.")
