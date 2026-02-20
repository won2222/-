import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import io
import re

# --- [1] 부장님 정예 설정 ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "매립", "재활용"]

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v5100", layout="wide")
st.title("📡 THE RADAR v5100.0")
st.success("🎯 기관별 고유 언어(G2B-12자리, LH-8자리, Kwater-6자리) 완벽 분리 적용")

if st.sidebar.button("🚀 기관별 맞춤 수색 개시", type="primary"):
    final_list = []
    now = datetime.now()
    
    # 🎯 [기관별 전용 날짜 생성] - 부장님 코드 방식
    g2b_start = (now - timedelta(days=7)).strftime("%Y%m%d") + "0000"
    g2b_end = now.strftime("%Y%m%d") + "2359"
    std_8_start = (now - timedelta(days=7)).strftime("%Y%m%d")
    std_8_end = now.strftime("%Y%m%d")
    kwater_month = now.strftime("%Y%m")

    status_st = st.empty()

    # --- 1. 나라장터 (12자리 언어) ---
    status_st.info("📡 [나라장터] 12자리 규격으로 접근 중...")
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': g2b_start, 'inqryEndDt': g2b_end, 'bidNtceNm': kw}
            res = requests.get(url_g2b, params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                final_list.append({'출처': 'G2B', '번호': it.get('bidNtceNo'), '공고명': it.get('bidNtceNm'), '기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '마감': it.get('bidClseDt')})
    except: pass

    # --- 2. LH (8자리 언어) ---
    status_st.info("📡 [LH포털] 8자리 규격으로 접근 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'tndrbidRegDtStart': std_8_start, 'tndrbidRegDtEnd': std_8_end, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text).strip())
        for item in root.findall('.//item'):
            bid_nm = item.findtext('bidnmKor', '')
            if any(kw in bid_nm for kw in KEYWORDS):
                final_list.append({'출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm, '기관': 'LH공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), '마감': item.findtext('openDtm')})
    except: pass

    # --- 3. 국방부 (v169 정예 언어) ---
    status_st.info("📡 [국방부] v169 정밀 예산 엔진 가동 중...")
    try:
        for bt in ['bid', 'priv']:
            url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
            res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json'}, timeout=15).json()
            items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for it in ([items_d] if isinstance(items_d, dict) else items_d):
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                if any(kw in bid_nm for kw in KEYWORDS):
                    # 부장님 특유의 예산 or 연산 로직
                    budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                    final_list.append({'출처': f'D2B({bt})', '번호': it.get('pblancNo') or it.get('dcsNo'), '공고명': bid_nm, '기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '마감': it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')})
    except: pass

    # --- 4. 수자원공사 (6자리 언어) ---
    status_st.info("📡 [수자원공사] 6자리 월간 규격 적용 중...")
    try:
        for kw in ["폐기물", "부유물", "식물성"]:
            res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", params={'serviceKey': SERVICE_KEY, 'searchDt': kwater_month, 'bidNm': kw, '_type': 'json'}, timeout=10).json()
            k_items = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for kit in ([k_items] if isinstance(k_items, dict) else k_items):
                final_list.append({'출처': 'Kwater', '번호': kit.get('tndrPbanno'), '공고명': kit.get('tndrPblancNm'), '기관': '한국수자원공사', '예산': 0, '마감': kit.get('tndrPblancEnddt')})
    except: pass

    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호'])
        st.success(f"✅ 작전 완료! 부장님 맞춤 언어로 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("⚠️ 각 기관 규격에 맞춰 수색했으나 현재 진행 중인 공고가 없습니다.")
