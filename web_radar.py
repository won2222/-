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

# --- [1] 글로벌 변수 및 설정 (에러 방지 핵심) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 부장님 v28.5 지정 키워드 및 필터
G2B_KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성"]
LH_KEYWORDS = ["폐기물", "폐목재", "식물성", "임목", "가연성"] # LH는 시설 위주로 핵심만
TARGET_LICENSES = ['6786', '6770', '1226', '1227']
MUST_PASS = ['경기도', '평택시', '화성시', '서울특별시', '서울', '인천', '전국', '경기']

# 🎯 시간 변수 전역 선언 (today_str 에러 완벽 해결)
KST = pytz.timezone('Asia/Seoul')
now = datetime.now(KST)
today_str = now.strftime("%Y%m%d")
s_date_4 = (now - timedelta(days=4)).strftime("%Y%m%d")
s_date_7 = (now - timedelta(days=7)).strftime("%Y%m%d")

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v2200", layout="wide")
st.title("📡 THE RADAR v2200.0")
st.info("🎯 엔진 분리 완료: 나라장터(JSON) / LH(XML) 독립 수색 및 변수 오류 수정")

if st.sidebar.button("🚀 독립 엔진 통합 수색", type="primary"):
    final_list = []
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 🎯 ENGINE A: 나라장터 (G2B - JSON 방식) ---
        status_st.info("📡 [ENGINE A] 나라장터 수색 중... (면허/지역 상세 필터)")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        
        for i, kw in enumerate(G2B_KEYWORDS):
            prog.progress((i + 1) / (len(G2B_KEYWORDS) * 2))
            try:
                time.sleep(0.15)
                # 나라장터는 8자리 날짜 포맷 사용
                params = {
                    'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 
                    'inqryDiv': '1', 'inqryBgnDt': s_date_4 + '0000', 
                    'inqryEndDt': today_str + '2359', 'bidNtceNm': kw
                }
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=params, timeout=10).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                
                for it in ([items] if isinstance(items, dict) else items):
                    b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(3)
                    
                    # 면허/지역 2차 필터 (v28.5 로직)
                    l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'ServiceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                    lic_str = str(l_res.get('response', {}).get('body', {}).get('items', []))
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'ServiceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                    reg_str = str(r_res.get('response', {}).get('body', {}).get('items', []))
                    
                    lic_ok = any(code in lic_str for code in TARGET_LICENSES) or "[]" in lic_str
                    reg_ok = any(area in reg_str for area in MUST_PASS)
                    
                    if lic_ok and reg_ok:
                        final_list.append({
                            '출처': '나라장터', '번호': b_no, '공고명': it.get('bidNtceNm'), 
                            '수요기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))),
                            '지역': reg_str[:50], '마감일': format_date_clean(it.get('bidClseDt')), 
                            'URL': it.get('bidNtceDtlUrl')
                        })
            except: continue

        # --- 🎯 ENGINE B: LH (e-Bid - XML 방식) ---
        status_st.info("📡 [ENGINE B] LH 시설공사 수색 중... (XML 독립 엔진)")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            # LH 전용 파라미터 (pageNo 포함)
            params_lh = {
                'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 
                'tndrbidRegDtStart': s_date_7, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'
            }
            res_lh = requests.get(url_lh, params=params_lh, headers=HEADERS, timeout=20)
            res_lh.encoding = res_lh.apparent_encoding
            
            # LH 전용 XML 파싱 로직
            lh_raw = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
            root = ET.fromstring(f"<root>{lh_raw}</root>")
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in LH_KEYWORDS):
                    final_list.append({
                        '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm,
                        '수요기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                        '지역': '전국/공고참조', '마감일': format_date_clean(item.findtext('openDtm')),
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
        except: pass

        # --- [결과 출력] ---
        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 수색 완료! 총 {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 통합 전략 리포트 저장", data=output.getvalue(), file_name=f"RADAR_v2200_{today_str}.xlsx")
        else:
            st.warning("⚠️ 포착된 공고가 없습니다. 날짜나 키워드를 확인해 보세요.")
            
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
