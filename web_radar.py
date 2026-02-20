import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 부장님 정예 커스텀 설정 (v169 기반) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 부장님 v169 정예 키워드 (18종)
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
            "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
MUST_PASS = ['경기도', '평택시', '화성시', '서울특별시', '서울', '인천', '전국']

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v6700", layout="wide")
st.title("📡 THE RADAR v6700.0")
st.success("🎯 부장님 지시 준수: LH 시설공사(Gb:1) 고정 + v169 3사 통합 엔진")

if st.sidebar.button("🚀 v169 통합 정밀 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 부장님 v169 날짜 방식
    s_date_api = (now - timedelta(days=4)).strftime("%Y%m%d")
    today_api = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=4)).strftime("%Y%m%d")
    
    status_st = st.empty()

    # --- 1. 나라장터 (v169 로직) ---
    status_st.info("📡 [1/3] 나라장터(G2B) 수색 중...")
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date_api+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b, params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                final_list.append({'출처': '1.나라장터', '번호': it.get('bidNtceNo'), '공고명': it.get('bidNtceNm'), '수요기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역': '공고참조', '마감일': clean_date_strict(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')})
    except: pass

    # --- 2. LH (부장님 오더: 시설공사 Gb:1 고정) ---
    status_st.info("📡 [2/3] LH 시설공사(Gb:1) CDATA 파쇄 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        # 🎯 부장님 지시사항: cstrtnJobGb는 무조건 '1'
        p_lh = {'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 'tndrbidRegDtStart': s_date_api, 'tndrbidRegDtEnd': today_api, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        res_lh.encoding = res_lh.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        for item in root.findall('.//item'):
            bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
            if any(kw in bid_nm for kw in KEYWORDS):
                final_list.append({'출처': '2.LH(시설)', '번호': item.findtext('bidNum'), '공고명': bid_nm, '수요기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt'), errors='coerce') or 0), '지역': '전국', '마감일': clean_date_strict(item.findtext('openDtm')), 'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"})
    except: pass

    # --- 3. 국방부 (v169 예산 엔진) ---
    status_st.info("📡 [3/3] 국방부 정밀 수색 중...")
    try:
        for bt in ['bid', 'priv']:
            url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
            res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, headers=HEADERS, timeout=15).json()
            items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for it in ([items_d] if isinstance(items_d, dict) else items_d):
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                if any(kw in bid_nm for kw in KEYWORDS):
                    budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                    final_list.append({'출처': '3.D2B', '번호': it.get('pblancNo') or it.get('dcsNo'), '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': '공고참조', '마감일': clean_date_strict(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'})
    except: pass

    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
        st.success(f"✅ 수색 완료! 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 v169 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_v169_{today_api}.xlsx")
    else:
        st.warning("🚨 현재 조건에 맞는 공고가 없습니다.")
