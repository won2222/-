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

# 기관별 맞춤 키워드 (부장님 오더 반영)
G2B_D2B_KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "재활용"]
LH_KEYWORDS_ONLY = '폐목재|임목|낙엽' # 🎯 LH 전용 정예 키워드
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

def lh_korean_cleaner(text):
    if not text: return ""
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v7500", layout="wide")
st.title("📡 THE RADAR v7500.0")

# --- [3] 사이드바: LH 전용 날짜 제어 ---
st.sidebar.header("📅 LH 전용 수색 설정")
lh_start_date = st.sidebar.date_input("LH 시작일", datetime(2026, 2, 13))
lh_end_date = st.sidebar.date_input("LH 종료일", datetime(2026, 2, 20))
st.sidebar.caption("※ LH는 위 설정된 날짜의 공고를 수색합니다.")
st.sidebar.divider()
st.sidebar.info("💡 나라장터/국방부/수자원/가스공사는 최근 데이터 자동 수색")

if st.sidebar.button("🔍 5대 기관 통합 정밀 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 날짜 규격화
    lh_s = lh_start_date.strftime("%Y%m%d")
    lh_e = lh_end_date.strftime("%Y%m%d")
    g2b_s = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_api = now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m') # 수자원공사용
    kogas_start = (now - timedelta(days=180)).strftime("%Y%m%d") # 가스공사 6개월

    status_st = st.empty()

    # --- 1. LH (e-Bid) : 사이드바 날짜 + 정예 키워드 ---
    status_st.info(f"📡 [1/5] LH 시설공사 정예 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 
                'tndrbidRegDtStart': lh_s, 'tndrbidRegDtEnd': lh_e, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        res_lh.encoding = res_lh.apparent_encoding
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

    # --- 2. 나라장터 (G2B) ---
    status_st.info("📡 [2/5] 나라장터 수색 중...")
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in G2B_D2B_KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '50', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': g2b_s+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b, params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                final_list.append({
                    '출처': 'G2B', '번호': it.get('bidNtceNo'), '공고명': it.get('bidNtceNm'),
                    '기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))),
                    '마감': clean_date_strict(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')
                })
    except: pass

    # --- 3. 국방부 (D2B) : 통합공고번호 정밀 수집 ---
    status_st.info("📡 [3/5] 국방부 통합공고번호 정밀 수색 중...")
    try:
        for bt in ['bid', 'priv']:
            url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
            res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json'}, timeout=15).json()
            items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for it in ([items_d] if isinstance(items_d, dict) else items_d):
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                if any(kw in bid_nm for kw in G2B_D2B_KEYWORDS):
                    # 🎯 통합공고번호(g2bPblancNo)가 있으면 우선 사용
                    b_no = it.get('g2bPblancNo') or it.get('pblancNo') or it.get('dcsNo')
                    final_list.append({
                        '출처': 'D2B', '번호': b_no, '공고명': bid_nm, '기관': it.get('ornt'), 
                        '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or it.get('budgetAmount') or 0)),
                        '마감': clean_date_strict(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')),
                        'URL': 'https://www.d2b.go.kr'
                    })
    except: pass

    # --- 4. 수자원공사 (K-water) : v181 로직 이식 ---
    status_st.info("📡 [4/5] 수자원공사(K-water) 키워드 필터링 중...")
    for kw in KWATER_KEYWORDS:
        try:
            url_k = "http://apis.data.go.kr/B500001/ebid/tndr3/servcList"
            p_k = {'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '100', '_type': 'json', 'searchDt': search_month, 'bidNm': kw}
            res_k = requests.get(url_k, params=p_k, timeout=10).json()
            items_k = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for it in ([items_k] if isinstance(items_k, dict) else items_k):
                title = it.get('tndrPblancNm', '-')
                if any(k in title for k in KWATER_KEYWORDS):
                    final_list.append({
                        '출처': 'K-water', '번호': it.get('tndrPbanno', '-'), '공고명': title,
                        '기관': it.get('cntrctDeptNm', '수자원공사'), '예산': 0,
                        '마감': clean_date_strict(it.get('tndrPblancEnddt')), 'URL': 'https://ebid.kwater.or.kr'
                    })
        except: continue

    # --- 5. 가스공사 (KOGAS) : v193 로직 이식 ---
    status_st.info("📡 [5/5] 가스공사(KOGAS) 6개월 데이터 수집 중...")
    try:
        url_kg = "http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList"
        p_kg = {'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 'DOCDATE_START': kogas_start}
        res_kg = requests.get(url_kg, params=p_kg, timeout=15)
        root_kg = ET.fromstring(res_kg.text)
        for it in root_kg.findall('.//item'):
            title = it.findtext('NOTICE_NAME') or '-'
            if any(kw in title for kw in KOGAS_KEYWORDS):
                final_list.append({
                    '출처': 'KOGAS', '번호': it.findtext('NOTICE_CODE') or '-', '공고명': title,
                    '기관': '한국가스공사', '예산': 0,
                    '마감': clean_date_strict(it.findtext('END_DT')), 'URL': 'https://k-ebid.kogas.or.kr'
                })
    except: pass

    # --- 최종 출력 ---
    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감'])
        st.success(f"✅ 5대 기관 통합 수색 완료! 총 {len(df)}건 확보.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 5대 기관 통합 리포트 다운로드", data=output.getvalue(), file_name=f"INTEGRATED_RADAR_{today_api}.xlsx")
    else:
        st.warning("⚠️ 현재 조건에 맞는 공고가 없습니다.")
