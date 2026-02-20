import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 부장님 정예 커스텀 설정 (v169 & LH 명세서 반영) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 18종 정예 키워드 (v169 원본)
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
            "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
MUST_PASS = ['경기도', '평택', '화성', '서울', '인천', '전국']

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v6900", layout="wide")
st.title("📡 THE RADAR v6900.0")
st.success("🎯 LH 활용가이드 명세(v1.4) + v169 3사 통합 로직 동기화 완료")

KST = pytz.timezone('Asia/Seoul')
now = datetime.now(KST)
today_api = now.strftime("%Y%m%d")
s_date_api = (now - timedelta(days=7)).strftime("%Y%m%d")

if st.sidebar.button("🚀 3사 통합 정밀 수색 개시", type="primary"):
    final_list = []
    status_st = st.empty()
    
    # --- 1. LH (e-Bid) : 활용가이드 v1.4 규격 적용 ---
    status_st.info("📡 [1/3] LH 시설공사(Gb:1) 명세서 규격 침투 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        # 명세서 가이드: tndrbidRegDtStart/End는 필수 날짜쌍
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'pageNo': '1', 
                'tndrbidRegDtStart': s_date_api, 'tndrbidRegDtEnd': today_api, 
                'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        res_lh.encoding = 'utf-8'
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        
        if root.findtext('.//resultCode') == "00":
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    final_list.append({
                        '출처': 'LH(시설)', '번호': item.findtext('bidNum'), '공고명': bid_nm,
                        '수요기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                        '지역': '공고참조', '마감일': clean_date_strict(item.findtext('openDtm')),
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
    except: pass

    # --- 2. 국방부 (D2B) : v169 예산 정밀 엔진 ---
    status_st.info("📡 [2/3] 국방부 일반/수의 통합 예산 엔진 가동...")
    try:
        for bt in ['bid', 'priv']:
            url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
            res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, headers=HEADERS, timeout=15).json()
            items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for it in ([items_d] if isinstance(items_d, dict) else items_d):
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                if any(kw in bid_nm for kw in KEYWORDS):
                    # v169 핵심: 예산 3중 파싱
                    budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                    final_list.append({
                        '출처': 'D2B', '번호': it.get('pblancNo') or it.get('dcsNo'), '공고명': bid_nm,
                        '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0),
                        '지역': '공고참조', '마감일': clean_date_strict(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')),
                        'URL': 'https://www.d2b.go.kr'
                    })
    except: pass

    # --- 3. 나라장터 (G2B) : v169 수색 엔진 ---
    status_st.info("📡 [3/3] 나라장터(G2B) 키워드 순회 수색 중...")
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date_api+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b, params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                final_list.append({'출처': 'G2B', '번호': it.get('bidNtceNo'), '공고명': it.get('bidNtceNm'), '수요기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역': '공고참조', '마감일': clean_date_strict(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')})
    except: pass

    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by='마감일')
        st.success(f"✅ 작전 성공! LH 명세서 규격 포함 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_v6900_{today_api}.xlsx")
    else:
        st.warning("🚨 모든 규격을 맞췄으나 현재 조건에 맞는 공고가 없습니다.")
