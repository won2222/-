import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import time
import pytz

# --- [1] 부장님 정예 설정 (v169/v90 통합) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# LH 전용 (v90 정밀 키워드)
LH_KEYWORDS_REGEX = '폐목재|임목|목재|나무|벌채|뿌리|폐기물|운반|재활용'
# 국방부/공용 키워드
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "임목"]

def lh_korean_cleaner(text):
    if not text: return ""
    # v90 핵심: CDATA 장벽 파괴
    text = re.sub(r'<!\[CDATA\[|\]\]>', '', text)
    return text.strip()

def format_date_clean(val):
    if not val: return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v6300", layout="wide")
st.title("📡 THE RADAR v6300.0")
st.error("🚀 LH(v90) 시설공사 정밀 검증 모드 가동 (국방부 통합)")

if st.sidebar.button("🔍 LH & 국방부 정밀 수색", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 🎯 날짜 파라미터 (LH: 2월 집중 / 국방부: 7일)
    lh_start, lh_end = '20260201', '20260228'
    d2b_start = (now - timedelta(days=7)).strftime("%Y%m%d")
    d2b_future = (now + timedelta(days=7)).strftime("%Y%m%d")
    
    status_st = st.empty()
    log_st = st.expander("🛠️ 기관별 수색 로그", expanded=True)

    # --- 1. LH (e-Bid) : 부장님 v90.0 로직 100% 동기화 ---
    status_st.info("📡 [LH포털] v90.0 시설공사 검증 엔진 가동...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        params_lh = {
            'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500',
            'tndrbidRegDtStart': lh_start, 'tndrbidRegDtEnd': lh_end,
            'cstrtnJobGb': '1' # 시설공사 전용
        }
        res_lh = requests.get(url_lh, params=params_lh, timeout=20)
        res_lh.encoding = res_lh.apparent_encoding
        raw_text = res_lh.text
        
        # 🎯 v90 핵심: XML 루트 및 CDATA 정밀 청소
        clean_xml = re.sub(r'<\?xml.*\?>', '', raw_text).strip()
        
        # 🎯 v90 핵심: resultCode 00 검증 로직
        if "<resultCode>00</resultCode>" in clean_xml:
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                raw_nm = item.findtext('bidnmKor', '')
                clean_nm = lh_korean_cleaner(raw_nm)
                
                # 정규표현식 매칭
                if re.search(LH_KEYWORDS_REGEX, clean_nm, re.IGNORECASE):
                    final_list.append({
                        '출처': 'LH(시설)', '번호': item.findtext('bidNum'),
                        '공고명': clean_nm, '수요기관': '한국토지주택공사',
                        '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0),
                        '마감일': format_date_clean(item.findtext('openDtm')),
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
            log_st.success(f"✅ LH 시설공사 수색 완료")
        else:
            log_st.error(f"❌ LH 서버 응답 오류 (코드 00 아님)")
    except Exception as e:
        log_st.error(f"❌ LH 엔진 가동 실패: {e}")

    # --- 2. 국방부 (D2B) : v161/169 통합 엔진 ---
    status_st.info("📡 [국방부] 일반/수의 통합 수색 중...")
    try:
        url_d = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
        res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json'}, timeout=15).json()
        items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        for it in ([items_d] if isinstance(items_d, dict) else items_d):
            bid_nm = it.get('bidNm', '')
            if any(kw in bid_nm for kw in KEYWORDS):
                final_list.append({
                    '출처': 'D2B', '번호': it.get('pblancNo') or it.get('dcsNo'),
                    '공고명': bid_nm, '수요기관': it.get('ornt'),
                    '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or it.get('budgetAmount') or 0)),
                    '마감일': format_date_clean(it.get('biddocPresentnClosDt')),
                    'URL': 'https://www.d2b.go.kr'
                })
        log_st.success(f"✅ 국방부 수색 완료")
    except: pass

    # --- [결과 출력] ---
    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by='마감일')
        st.success(f"✅ 수색 작전 완료! LH 포함 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
    else:
        st.warning("⚠️ 모든 규격을 맞췄으나 현재 조건에 맞는 공고가 없습니다.")
