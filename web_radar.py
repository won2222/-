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

# --- [1] 정예 커스텀 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음', '부산', '경남']

KWATER_DETAIL_BASE = "https://ebid.kwater.or.kr/wq/index.do?w2xPath=/ui/index.xml&view=/bidpblanc/bidpblancsttus/BIDBD32000002.xml&tndrPbanno="
KOGAS_DIRECT_URL = "https://bid.kogas.or.kr:9443/supplier/index.jsp"

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR", layout="wide")
st.title("📡 THE RADAR")
st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE (7-DAY DEADLINE)")
st.divider()

if st.sidebar.button("🔍 7일 내 마감 공고 정밀 수색", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 🎯 마감일 기준 필터: 현재부터 7일 뒤까지
    deadline_start = now.strftime("%Y%m%d%H%M")
    deadline_end = (now + timedelta(days=7)).strftime("%Y%m%d%H%M")
    
    # 🎯 등록일 검색 범위: 마감이 임박한 예전 공고를 잡기 위해 20일 전부터 조회
    s_date = (now - timedelta(days=20)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    kogas_start = (now - timedelta(days=14)).strftime("%Y%m%d")
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 (G2B) ---
        status_st.info("📡 [PHASE 1] G2B 수색 중 (20일 내 등록건 분석)...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / 100)
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=7).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    clse_dt = it.get('bidClseDt', '')
                    # 🎯 7일 이내 마감건만 필터링
                    if clse_dt and (deadline_start <= clse_dt <= deadline_end):
                        b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                        # 지역/면허 체크 생략(속도 우선) 또는 필요 시 추가 로직
                        final_list.append({'출처':'G2B', '번호':b_no, '공고명':it['bidNtceNm'], '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역':'상세참조', '마감일':format_date_clean(clse_dt), 'URL':it.get('bidNtceDtlUrl')})
            except: continue

        # --- 2. LH (공사 + 용역) ---
        for job_gb, job_nm in [('1', '공사'), ('5', '용역')]:
            status_st.info(f"📡 [PHASE 2] LH {job_nm} 채널 수색 중...")
            try:
                url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
                p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': job_gb}
                res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=12)
                res_lh.encoding = res_lh.apparent_encoding
                root = ET.fromstring(f"<root>{re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()}</root>")
                for item in root.findall('.//item'):
                    open_dtm = item.findtext('openDtm', '')
                    if open_dtm and (deadline_start <= open_dtm <= deadline_end):
                        bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                        if any(kw in bid_nm for kw in KEYWORDS):
                            b_no = item.findtext('bidNum')
                            final_list.append({'출처':f'LH({job_nm})', '번호':b_no, '공고명':bid_nm, '수요기관':'LH', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), '지역':'전국', '마감일':format_date_clean(open_dtm), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"})
            except: continue

        # --- 3. 가스공사 (KOGAS) ---
        status_st.info("📡 [PHASE 3] KOGAS 수색 중...")
        try:
            res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': kogas_start}, timeout=15)
            root_kg = ET.fromstring(res_kg.text)
            for item in root_kg.findall('.//item'):
                end_dt = item.findtext('END_DT') # 마감일
                if end_dt and (deadline_start[:8] <= end_dt[:8] <= deadline_end[:8]):
                    title = item.findtext('NOTICE_NAME') or '-'
                    if any(kw in title for kw in KOGAS_KEYWORDS):
                        final_list.append({'출처': 'K-water/KOGAS', '번호': item.findtext('NOTICE_CODE') or '-', '공고명': title, '수요기관': '가스공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(end_dt), 'URL': KOGAS_DIRECT_URL})
        except: pass

        # --- 최종 출력 ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 향후 7일 내 마감되는 공고 {len(df)}건을 발견했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='7DAY_STRATEGY')
            st.download_button(label="📥 7일 마감 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_7DAY_{today_str}.xlsx")
        else:
            st.warning("⚠️ 7일 이내 마감 예정인 공고가 없습니다.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
