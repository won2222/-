import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [부장님 설정값 동기화] ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "식물성", "임목"]
LH_KEYWORDS_REGEX = '폐목재|임목|목재|나무|벌채|뿌리|폐기물|운반|재활용'

def format_date(val):
    if not val: return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else val

st.set_page_config(page_title="THE RADAR v7100", layout="wide")
st.title("📡 THE RADAR v7100.0")
st.info("🎯 엔진 순차 가동 모드: 1차 JSON(G2B/D2B) -> 2차 XML(LH) 수색 및 통합")

if st.sidebar.button("🚀 2단계 순차 수색 개시", type="primary"):
    total_data = [] # 모든 데이터가 담길 통합 바구니
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 날짜 규격 설정
    s_date_8 = (now - timedelta(days=7)).strftime("%Y%m%d")
    s_date_12 = s_date_8 + "0000"
    today_8 = now.strftime("%Y%m%d")
    today_12 = today_8 + "2359"
    
    status_st = st.empty()

    # ==========================================================
    # ⚙️ 1단계: JSON 엔진 가동 (G2B & D2B)
    # ==========================================================
    status_st.info("📡 [1단계] 나라장터 & 국방부 수색 중 (JSON)")
    
    # 1-1. 나라장터
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '50', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date_12, 'inqryEndDt': today_12, 'bidNtceNm': kw}
            res = requests.get(url_g2b, params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                total_data.append({'출처': 'G2B', '번호': it.get('bidNtceNo'), '공고명': it.get('bidNtceNm'), '기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '마감': format_date(it.get('bidClseDt'))})
    except: pass

    # 1-2. 국방부 (v169 로직)
    try:
        url_d = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
        res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json'}, timeout=15).json()
        items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        for it in ([items_d] if isinstance(items_d, dict) else items_d):
            bid_nm = it.get('bidNm', '')
            if any(kw in bid_nm for kw in KEYWORDS):
                budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                total_data.append({'출처': 'D2B', '번호': it.get('pblancNo'), '공고명': bid_nm, '기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '마감': format_date(it.get('biddocPresentnClosDt'))})
    except: pass

    # ==========================================================
    # ⚙️ 2단계: XML 엔진 가동 (LH 시설공사)
    # ==========================================================
    status_st.info("📡 [2단계] LH 시설공사 수색 중 (XML)")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        # 활용가이드 v1.4 필수 파라미터 적용 [cite: 21, 23]
        p_lh = {
            'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'pageNo': '1', 
            'tndrbidRegDtStart': s_date_8, 'tndrbidRegDtEnd': today_8, 
            'cstrtnJobGb': '1' # 부장님 오더: 시설공사 고정
        }
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        res_lh.encoding = 'utf-8'
        
        # v90 필살기: CDATA 파쇄 및 루트 생성 [cite: 28]
        raw_xml = res_lh.text
        clean_xml = re.sub(r'<!\[CDATA\[|\]\]>', '', raw_xml).strip()
        clean_xml = re.sub(r'<\?xml.*\?>', '', clean_xml).strip()
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        
        if root.findtext('.//resultCode') == "00": # [cite: 25]
            for item in root.findall('.//item'):
                bid_nm = item.findtext('bidnmKor', '').strip()
                if re.search(LH_KEYWORDS_REGEX, bid_nm, re.IGNORECASE):
                    total_data.append({
                        '출처': 'LH(시설)', 
                        '번호': item.findtext('bidNum'), 
                        '공고명': bid_nm, 
                        '기관': 'LH공사', 
                        '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), 
                        '마감': format_date(item.findtext('openDtm'))
                    })
    except: pass

    # ==========================================================
    # 📊 데이터 통합 정렬 및 출력
    # ==========================================================
    status_st.empty()
    if total_data:
        df = pd.DataFrame(total_data).drop_duplicates(subset=['번호'])
        df['마감'] = df['마감'].astype(str)
        df = df.sort_values(by='마감')
        
        # 대시보드 스코어보드
        st.success(f"✅ 통합 수색 완료! 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        # 엑셀 저장
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 2단계 통합 리포트 다운로드", data=output.getvalue(), file_name=f"FINAL_RADAR_{today_8}.xlsx")
    else:
        st.warning("⚠️ 모든 엔진을 돌렸으나 검색 결과가 없습니다.")
