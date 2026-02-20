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

# 정예 키워드 및 필터 (v169 기반 18종 확장)
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
            "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
LH_KEYWORDS_REGEX = '폐목재|임목|목재|나무|벌채|뿌리|폐기물|운반|재활용'

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

def lh_korean_cleaner(text):
    if not text: return ""
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v7400", layout="wide")
st.title("📡 THE RADAR v7400.0")

# --- [3] 사이드바: LH 전용 날짜 제어 (부장님 오더) ---
st.sidebar.header("📅 LH 전용 수색 설정")
lh_start_date = st.sidebar.date_input("LH 시작일", datetime(2026, 2, 13))
lh_end_date = st.sidebar.date_input("LH 종료일", datetime(2026, 2, 20))
st.sidebar.caption("※ LH는 위 설정된 날짜의 공고를 수색합니다.")
st.sidebar.divider()
st.sidebar.info("💡 나라장터/국방부는 오늘 기준 최근 7일 및 마감 예정 건을 자동으로 수색합니다.")

if st.sidebar.button("🔍 3사 통합 정밀 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 날짜 규격화
    lh_s = lh_start_date.strftime("%Y%m%d")
    lh_e = lh_end_date.strftime("%Y%m%d")
    g2b_s = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_api = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=7)).strftime("%Y%m%d")
    
    status_st = st.empty()

    # --- 1. LH (e-Bid) : 사이드바 날짜 + v90.0 시설공사 로직 ---
    status_st.info(f"📡 [LH포털] {lh_s}~{lh_e} 시설공사 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {
            'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500',
            'tndrbidRegDtStart': lh_s, 'tndrbidRegDtEnd': lh_e,
            'cstrtnJobGb': '1' 
        }
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        res_lh.encoding = res_lh.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        if "<resultCode>00</resultCode>" in clean_xml:
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                bid_nm = lh_korean_cleaner(item.findtext('bidnmKor', ''))
                if re.search(LH_KEYWORDS_REGEX, bid_nm, re.IGNORECASE):
                    final_list.append({
                        '출처': '2.LH(시설)', '번호': item.findtext('bidNum'), '공고명': bid_nm,
                        '기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                        '마감': clean_date_strict(item.findtext('openDtm')),
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
    except: pass

    # --- 2. 나라장터 (G2B) : v169 로직 ---
    status_st.info("📡 [나라장터] 최근 7일 키워드 순회 중...")
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '50', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': g2b_s+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b, params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                final_list.append({
                    '출처': '1.G2B', '번호': it.get('bidNtceNo'), '공고명': it.get('bidNtceNm'),
                    '기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))),
                    '마감': clean_date_strict(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')
                })
    except: pass

    # --- 3. 국방부 (D2B) : v161/169 통합 엔진 ---
    status_st.info("📡 [국방부] 일반/수의 마감 예정 건 수색 중...")
    try:
        for bt in ['bid', 'priv']:
            url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
            res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json'}, headers=HEADERS, timeout=15).json()
            items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for it in ([items_d] if isinstance(items_d, dict) else items_d):
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                if any(kw in bid_nm for kw in KEYWORDS):
                    budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                    final_list.append({
                        '출처': '3.D2B', '번호': it.get('pblancNo') or it.get('dcsNo'), '공고명': bid_nm,
                        '기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0),
                        '마감': clean_date_strict(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')),
                        'URL': 'https://www.d2b.go.kr'
                    })
    except: pass

    # --- 최종 출력 ---
    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['출처', '마감'])
        st.success(f"✅ 수색 완료! 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 3사 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_HYBRID_{today_api}.xlsx")
    else:
        st.warning("⚠️ 현재 조건에 맞는 공고가 없습니다.")
