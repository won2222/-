import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 부장님 정예 세팅 (v169 & LH 명세서 규격) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "재활용"]
LH_KEYWORDS_REGEX = '폐목재|임목|목재|나무|벌채|뿌리|폐기물|운반|재활용'

def format_date(val):
    if not val: return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v7000", layout="wide")
st.title("📡 THE RADAR v7000.0")
st.success("🎯 엔진 이원화 완료: JSON(G2B/D2B) 엔진 & XML(LH) 엔진 개별 가동")

KST = pytz.timezone('Asia/Seoul')
now = datetime.now(KST)
today_api = now.strftime("%Y%m%d")
s_date_api = (now - timedelta(days=7)).strftime("%Y%m%d")

if st.sidebar.button("🚀 이원화 엔진 통합 수색 개시", type="primary"):
    g2b_list, lh_list, d2b_list = [], [], []
    status_st = st.empty()
    
    # ==========================================================
    # ⚙️ 엔진 A: JSON 엔진 (나라장터 & 국방부)
    # ==========================================================
    status_st.info("📡 [엔진 A] JSON 데이터(나라장터/국방부) 수색 중...")
    
    # 1. 나라장터 (G2B)
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date_api+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b, params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                g2b_list.append({'출처': 'G2B', '번호': it.get('bidNtceNo'), '공고명': it.get('bidNtceNm'), '기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '마감': format_date(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')})
    except: pass

    # 2. 국방부 (D2B)
    try:
        url_d = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
        res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json'}, timeout=15).json()
        items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        for it in ([items_d] if isinstance(items_d, dict) else items_d):
            bid_nm = it.get('bidNm', '')
            if any(kw in bid_nm for kw in KEYWORDS):
                d2b_list.append({'출처': 'D2B', '번호': it.get('pblancNo'), '공고명': bid_nm, '기관': it.get('ornt'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or 0)), '마감': format_date(it.get('biddocPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'})
    except: pass

    # ==========================================================
    # ⚙️ 엔진 B: XML 엔진 (LH 시설공사 전용)
    # ==========================================================
    status_st.info("📡 [엔진 B] XML 데이터(LH 시설공사) 파싱 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        # 명세서 규격 준수: tndrbidRegDtStart/End 8자리
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'pageNo': '1', 'tndrbidRegDtStart': s_date_api, 'tndrbidRegDtEnd': today_api, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        res_lh.encoding = 'utf-8'
        
        # CDATA 파쇄 및 루트 강제 생성
        clean_xml = re.sub(r'<\?xml.*\?>|<!\[CDATA\[|\]\]>', '', res_lh.text).strip()
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        
        if root.findtext('.//resultCode') == "00":
            for item in root.findall('.//item'):
                bid_nm = item.findtext('bidnmKor', '').strip()
                if re.search(LH_KEYWORDS_REGEX, bid_nm, re.IGNORECASE):
                    lh_list.append({'출처': 'LH(시설)', '번호': item.findtext('bidNum'), '공고명': bid_nm, '기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), '마감': format_date(item.findtext('openDtm')), 'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"})
    except: pass

    # ==========================================================
    # 📊 데이터 병합 및 출력
    # ==========================================================
    status_st.empty()
    final_all = g2b_list + lh_list + d2b_list
    
    if final_all:
        df = pd.DataFrame(final_all).drop_duplicates(subset=['번호']).sort_values(by='마감')
        
        # 메트릭 현황판
        c1, c2, c3 = st.columns(3)
        c1.metric("G2B", f"{len(g2b_list)}건")
        c2.metric("LH", f"{len(lh_list)}건")
        c3.metric("D2B", f"{len(d2b_list)}건")
        
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        # 통합 엑셀 다운로드
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 이원화 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_V7000_{today_api}.xlsx")
    else:
        st.warning("🚨 두 엔진 모두에서 조건에 맞는 공고를 찾지 못했습니다.")
