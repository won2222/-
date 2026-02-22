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

# 키워드 세팅 (부장님 18종 확장 키워드 반영)
G2B_D2B_KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
LH_KEYWORDS_ONLY = '폐목재|임목|낙엽'
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

# v169 지역 필터 기준
MUST_PASS = ['경기도', '평택시', '화성시', '서울특별시', '서울', '인천', '전국']
EXCLUDE_LIST = ['충청', '전라', '강원', '경상', '제주', '부산', '대구', '광주', '대전', '울산', '세종', '충북', '충남', '경북', '경남', '전북', '전남']

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

def lh_korean_cleaner(text):
    if not text: return ""
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v8500", layout="wide")
st.title("📡 THE RADAR v8500.0")

# --- [3] 사이드바 설정 ---
st.sidebar.header("📅 LH 전용 수색 설정")
lh_start_date = st.sidebar.date_input("LH 시작일", datetime(2026, 2, 13))
lh_end_date = st.sidebar.date_input("LH 종료일", datetime(2026, 2, 20))
st.sidebar.divider()

if st.sidebar.button("🚀 5대 기관 통합 정밀 수색", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    lh_s = lh_start_date.strftime("%Y%m%d")
    lh_e = lh_end_date.strftime("%Y%m%d")
    s7 = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_api = now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m')
    kogas_start = (now - timedelta(days=180)).strftime("%Y%m%d")

    status_st = st.empty()

    # --- 1. 나라장터 (G2B) : v169 상세 분석 로직 기반 ---
    status_st.info("📡 [1/5] 나라장터(G2B) 지역 및 면허(업종) 분석 중...")
    try:
        url_g2b_base = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        g_raw = []
        # 키워드별 수집
        for kw in G2B_D2B_KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s7+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b_base + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                g_raw.append(it)
        
        if g_raw:
            df_g = pd.DataFrame(g_raw).drop_duplicates(subset=['bidNtceNo'])
            for _, row in df_g.iterrows():
                b_no = row['bidNtceNo']
                b_ord = str(row.get('bidNtceOrd', '00')).zfill(2)
                
                # ⚙️ 지역(Rgn) 및 면허(Instl) 정보 상세 조회 (v169 로직)
                reg_val = "제한없음"
                license_val = "상세참조"
                try:
                    # 지역 정보
                    r_res = requests.get(url_g2b_base + 'getBidPblancListInfoPrtcptPsblRgn', 
                                         params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=3).json()
                    regs = [str(ri.get('prtcptPsblRgnNm', '')) for ri in r_res.get('response', {}).get('body', {}).get('items', [])]
                    if regs: reg_val = ", ".join(list(set(regs)))
                    
                    # 면허/업종 정보
                    l_res = requests.get(url_g2b_base + 'getBidPblancListInfoPrtcptPsblInstl',
                                         params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=3).json()
                    lics = [str(li.get('instlNm', '')) for li in l_res.get('response', {}).get('body', {}).get('items', [])]
                    if lics: license_val = ", ".join(list(set(lics)))
                except: pass

                final_list.append({
                    '출처': 'G2B', '번호': b_no, '공고명': row['bidNtceNm'], '지역': reg_val, '면허': license_val,
                    '기관': row['dminsttNm'], '예산': int(pd.to_numeric(row.get('asignBdgtAmt', 0))), 
                    '마감': clean_date_strict(row.get('bidClseDt')), 'URL': row.get('bidNtceDtlUrl')
                })
    except: pass

    # --- 2. LH (e-Bid) ---
    status_st.info("📡 [2/5] LH 포털 분석 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        res_lh = requests.get(url_lh, params={'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 'tndrbidRegDtStart': lh_s, 'tndrbidRegDtEnd': lh_e, 'cstrtnJobGb': '1'}, timeout=15)
        res_lh.encoding = res_lh.apparent_encoding
        root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text).strip())
        for item in root.findall('.//item'):
            bid_nm = lh_korean_cleaner(item.findtext('bidnmKor', ''))
            if re.search(LH_KEYWORDS_ONLY, bid_nm, re.IGNORECASE):
                final_list.append({
                    '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm, '지역': '전국/공고참조', '면허': '상세참조',
                    '기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), 
                    '마감': clean_date_strict(item.findtext('openDtm')),
                    'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                })
    except: pass

    # --- 3. 국방부 (D2B) ---
    status_st.info("📡 [3/5] 국방부(D2B) 상세 분석 중...")
    try:
        url_d = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
        res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, headers=HEADERS).json()
        items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        for it in ([items_d] if isinstance(items_d, dict) else items_d):
            bid_nm = it.get('bidNm', '')
            if any(kw in bid_nm for kw in G2B_D2B_KEYWORDS):
                final_list.append({
                    '출처': 'D2B', '번호': it.get('g2bPblancNo') or it.get('pblancNo') or it.get('dcsNo'), 
                    '공고명': bid_nm, '지역': '상세확인', '면허': '상세확인',
                    '기관': it.get('ornt'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or 0)), 
                    '마감': clean_date_strict(it.get('biddocPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'
                })
    except: pass

    # --- 4. 수자원공사 (K-water) ---
    status_st.info("📡 [4/5] 수자원공사 분석 중...")
    for kw in KWATER_KEYWORDS:
        try:
            url_k = "http://apis.data.go.kr/B500001/ebid/tndr3/servcList"
            p_k = {'serviceKey': SERVICE_KEY, 'searchDt': search_month, 'bidNm': kw, '_type': 'json'}
            res_k = requests.get(url_k, params=p_k, timeout=10).json()
            items_k = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for kit in ([items_k] if isinstance(items_k, dict) else items_k):
                final_list.append({
                    '출처': 'K-water', '번호': kit.get('tndrPbanno'), '공고명': kit.get('tndrPblancNm'), 
                    '지역': '공고참조', '면허': '상세참조', '기관': kit.get('cntrctDeptNm', '수자원공사'),
                    '예산': 0, '마감': clean_date_strict(kit.get('tndrPblancEnddt')), 'URL': 'https://ebid.kwater.or.kr'
                })
        except: continue

    # --- 5. 가스공사 (KOGAS) ---
    status_st.info("📡 [5/5] 가스공사 분석 중...")
    try:
        url_kg = "http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList"
        res_kg = requests.get(url_kg, params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': kogas_start}, timeout=15)
        root_kg = ET.fromstring(res_kg.text)
        for it in root_kg.findall('.//item'):
            title = it.findtext('NOTICE_NAME') or ''
            if any(kw in title for kw in KOGAS_KEYWORDS):
                final_list.append({
                    '출처': 'KOGAS', '번호': it.findtext('NOTICE_CODE'), '공고명': title, 
                    '지역': '공고참조', '면허': '상세참조', '기관': '한국가스공사',
                    '예산': 0, '마감': clean_date_strict(it.findtext('END_DT')), 'URL': 'https://k-ebid.kogas.or.kr'
                })
    except: pass

    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호'])
        df = df.sort_values(by=['마감'])
        
        # 컬럼 순서 조정: 공고명 옆에 지역/면허 배치
        df = df[['출처', '번호', '공고명', '지역', '면허', '기관', '예산', '마감', 'URL']]
        
        st.success(f"✅ 작전 완료! 총 {len(df)}건 확보 (v169 정밀 분석 로직 적용)")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        # 엑셀 다운로드 파일 생성
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_V8500_{today_api}.xlsx")
    else:
        st.warning("⚠️ 검색된 공고가 없습니다.")
