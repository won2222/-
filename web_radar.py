import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 부장님 정예 커스텀 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 기관별 정예 키워드
LH_KEYWORDS_ONLY = '폐목재|임목|낙엽' # 🎯 LH는 부장님 오더대로 3종 고정
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]
GEN_KEYWORDS = ["폐기물", "운반", "폐목재", "임목", "가연성", "잔재물", "재활용"]

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else val

def lh_korean_cleaner(text):
    if not text: return ""
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v8100", layout="wide")
st.title("📡 THE RADAR v8100.0")

# --- [3] 사이드바: LH 전용 날짜 (LH 수색에만 독립 적용) ---
st.sidebar.header("📅 LH 전용 수색 설정")
lh_start_date = st.sidebar.date_input("LH 시작일", datetime(2026, 2, 13))
lh_end_date = st.sidebar.date_input("LH 종료일", datetime(2026, 2, 20))
st.sidebar.divider()
st.sidebar.info("💡 나라장터/국방부/수자원/가스공사는 자동 수색됩니다.")

if st.sidebar.button("🚀 5대 기관 통합 정밀 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 날짜 규격화
    lh_s = lh_start_date.strftime("%Y%m%d")
    lh_e = lh_end_date.strftime("%Y%m%d")
    g2b_s = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_api = now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m')
    kogas_start = (now - timedelta(days=180)).strftime("%Y%m%d")

    status_st = st.empty()

    # --- ⚙️ 1. LH (e-Bid) : 부장님이 성공시킨 그 로직 100% 복구 ---
    status_st.info(f"📡 [1/5] LH {lh_s}~{lh_e} 시설공사 정예 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 
                'tndrbidRegDtStart': lh_s, 'tndrbidRegDtEnd': lh_e, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        res_lh.encoding = res_lh.apparent_encoding
        # 🎯 부장님 필살기: CDATA 파쇄 및 <root> 감싸기
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        if "<resultCode>00</resultCode>" in clean_xml:
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                bid_nm = lh_korean_cleaner(item.findtext('bidnmKor', ''))
                if re.search(LH_KEYWORDS_ONLY, bid_nm, re.IGNORECASE):
                    final_list.append({
                        '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm,
                        '기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                        '마감': clean_date_strict(item.findtext('openDtm')),
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
    except: pass

    # --- ⚙️ 2. 국방부 (D2B) : 통합공고번호 서치 보강 ---
    status_st.info("📡 [2/5] 국방부 통합공고번호 정밀 수색 중...")
    try:
        url_d = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
        res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json'}, timeout=15).json()
        items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        for it in ([items_d] if isinstance(items_d, dict) else items_d):
            bid_nm = it.get('bidNm', '')
            if any(kw in bid_nm for kw in GEN_KEYWORDS):
                # 🎯 나라장터 통합번호(g2bPblancNo) 우선순위
                b_no = it.get('g2bPblancNo') or it.get('pblancNo') or it.get('dcsNo')
                final_list.append({
                    '출처': 'D2B', '번호': b_no, '공고명': bid_nm, '기관': it.get('ornt'), 
                    '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or 0)), 
                    '마감': clean_date_strict(it.get('biddocPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'
                })
    except: pass

    # --- ⚙️ 3. 나라장터 (G2B) ---
    status_st.info("📡 [3/5] 나라장터 수색 중...")
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in GEN_KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '50', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': g2b_s+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b, params=p, timeout=10).json()
            items_g = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items_g] if isinstance(items_g, dict) else items_g):
                final_list.append({'출처': 'G2B', '번호': it.get('bidNtceNo'), '공고명': it.get('bidNtceNm'), '기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '마감': clean_date_strict(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')})
    except: pass

    # --- ⚙️ 4. 수자원공사 (K-water) : v181 로직 반영 ---
    status_st.info("📡 [4/5] 수자원공사 정밀 수색 중...")
    for kw in KWATER_KEYWORDS:
        try:
            res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", params={'serviceKey': SERVICE_KEY, 'searchDt': search_month, 'bidNm': kw, '_type': 'json'}, timeout=10).json()
            items_k = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for kit in ([items_k] if isinstance(items_k, dict) else items_k):
                if any(k in kit.get('tndrPblancNm', '') for k in KWATER_KEYWORDS):
                    final_list.append({'출처': 'K-water', '번호': kit.get('tndrPbanno'), '공고명': kit.get('tndrPblancNm'), '기관': '수자원공사', '예산': 0, '마감': clean_date_strict(kit.get('tndrPblancEnddt')), 'URL': 'https://ebid.kwater.or.kr'})
        except: continue

    # --- ⚙️ 5. 가스공사 (KOGAS) : v193 로직 반영 ---
    status_st.info("📡 [5/5] 가스공사 6개월 데이터 분석 중...")
    try:
        res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': kogas_start}, timeout=15)
        root_kg = ET.fromstring(res_kg.text)
        for it in root_kg.findall('.//item'):
            nm = it.findtext('NOTICE_NAME') or ''
            if any(kw in nm for kw in KOGAS_KEYWORDS):
                final_list.append({'출처': 'KOGAS', '번호': it.findtext('NOTICE_CODE'), '공고명': nm, '기관': '가스공사', '예산': 0, '마감': clean_date_strict(it.findtext('END_DT')), 'URL': 'https://k-ebid.kogas.or.kr'})
    except: pass

    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감'])
        st.success(f"✅ 5대 기관 통합 수색 완료! 총 {len(df)}건 확보.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 5대 기관 통합 리포트 다운로드", data=output.getvalue(), file_name=f"INTEGRATED_RADAR_v8100.xlsx")
    else:
        st.warning("🚨 모든 엔진 가동 완료! 현재 조건에 맞는 공고가 없습니다.")
