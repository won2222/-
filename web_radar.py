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
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 키워드 세팅
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "재활용"]
LH_KEYWORDS_REGEX = '폐목재|임목|목재|나무|벌채|뿌리|폐기물|운반|재활용'
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

def lh_korean_cleaner(text):
    if not text: return ""
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

# --- [2] 대시보드 설정 ---
st.set_page_config(page_title="THE RADAR v6500", layout="wide")
st.title("📡 THE RADAR v6500.0")
st.success("🎯 LH(v90 시설공사) + 국방부(v161/v169) + 나라장터 통합 완료")

# 날짜 정의 (버튼 밖에서 정의하여 NameError 방지)
KST = pytz.timezone('Asia/Seoul')
now = datetime.now(KST)
today_str = now.strftime("%Y%m%d") # 파일명 및 조회용
s_date_7 = (now - timedelta(days=7)).strftime("%Y%m%d")

if st.sidebar.button("🔍 전 채널 통합 수색 시작", type="primary"):
    final_list = []
    status_st = st.empty()
    
    # --- 1. LH (v90.0 로직: 시설공사 타격) ---
    status_st.info("📡 [1/3] LH 시설공사(Gb:1) 데이터 파쇄 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        # 🎯 LH는 부장님 v90 방식대로 2월 전체 수색
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': '20260201', 'tndrbidRegDtEnd': '20260228', 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        res_lh.encoding = res_lh.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        
        if "<resultCode>00</resultCode>" in clean_xml:
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                bid_nm = lh_korean_cleaner(item.findtext('bidnmKor', ''))
                if re.search(LH_KEYWORDS_REGEX, bid_nm, re.IGNORECASE):
                    b_no = item.findtext('bidNum')
                    final_list.append({
                        '출처':'LH(시설)', '번호':b_no, '공고명':bid_nm, '수요기관':'한국토지주택공사', 
                        '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), 
                        '지역':'전국/공고참조', '마감일':format_date_clean(item.findtext('openDtm')), 
                        'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}"
                    })
    except: pass

    # --- 2. 국방부 (v161/v169 로직) ---
    status_st.info("📡 [2/3] 국방부 정밀 예산 엔진 가동...")
    d2b_configs = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'c': 'biddocPresentnClosDt'}, {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'c': 'prqudoPresentnClosDt'}]
    for cfg in d2b_configs:
        try:
            p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json'}
            res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, headers=HEADERS, timeout=15).json()
            items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            items_d = [items_d] if isinstance(items_d, dict) else items_d
            for it in items_d:
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                if any(kw in bid_nm for kw in KEYWORDS):
                    # 🎯 부장님 v161 핵심: 예산 3중 파싱
                    budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                    p_no = it.get('pblancNo') or it.get('dcsNo')
                    final_list.append({
                        '출처': f"D2B({cfg['t']})", '번호': p_no, '공고명': bid_nm, '수요기관': it.get('ornt'), 
                        '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': "공고참조", 
                        '마감일': format_date_clean(it.get(cfg['c'])), 'URL': 'https://www.d2b.go.kr'
                    })
        except: continue

    # --- 3. 나라장터 (G2B) ---
    status_st.info("📡 [3/3] 나라장터 면허/지역 수색 중...")
    try:
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in KEYWORDS:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '50', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date_7+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b, params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                final_list.append({'출처':'G2B', '번호':it.get('bidNtceNo'), '공고명':it.get('bidNtceNm'), '수요기관':it.get('dminsttNm'), '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역':'공고참조', '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
    except: pass

    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호'])
        df['마감일'] = df['마감일'].astype(str)
        df = df.sort_values(by=['마감일'])
        
        st.success(f"✅ 수색 작전 완료! LH와 국방부, 나라장터 통합 총 {len(df)}건 확보.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_INTEGRATED_{today_str}.xlsx")
    else:
        st.warning("🚨 통합 수색 결과가 없습니다. 조건을 확인해 주세요.")
