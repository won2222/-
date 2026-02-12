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

# --- [1] 부장님 정예 커스텀 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

# 기관별 전용 키워드 (보내주신 파일 기준)
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음', '부산', '경남']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR", layout="wide")
st.title("📡 THE RADAR")
st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE (CLASSIC RESTORED)")
st.divider()

if st.sidebar.button("🔍 전 기관 통합 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 날짜 파라미터
    s_date = (now - timedelta(days=7)).strftime("%Y%m%d") # 공고일 기준 (나라장터, LH)
    today_str = now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m') # 수자원공사용
    kogas_start = (now - timedelta(days=180)).strftime("%Y%m%d") # 가스공사 6개월
    target_end_day = (now + timedelta(days=7)).strftime("%Y%m%d") # 국방부 마감일 기준
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 (공고일 기준) ---
        status_st.info("📡 [PHASE 1] G2B 수색 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / 100)
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    if "전자입찰" not in it.get('bidMethdNm', ''): continue
                    final_list.append({'출처':'G2B', '번호':it.get('bidNtceNo'), '공고명':it.get('bidNtceNm'), '수요기관':it.get('dminsttNm'), '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역':'전국', '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
            except: continue

        # --- 2. LH (공고일 기준 / 공사+용역 통합) ---
        status_st.info("📡 [PHASE 2] LH 수색 중 (공사/용역 통합)...")
        for job_gb in ['1', '5']:
            try:
                url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
                p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': job_gb}
                res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=10)
                res_lh.encoding = res_lh.apparent_encoding
                root = ET.fromstring(f"<root>{re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()}</root>")
                for item in root.findall('.//item'):
                    bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                    if any(kw in bid_nm for kw in KEYWORDS):
                        final_list.append({'출처':f'LH({"공사" if job_gb=="1" else "용역"})', '번호':item.findtext('bidNum'), '공고명':bid_nm, '수요기관':'LH', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), '지역':'전국', '마감일':format_date_clean(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}&bidDegree=00"})
            except: pass

        # --- 3. 국방부 (마감일 기준) ---
        status_st.info("📡 [PHASE 3] D2B 수색 중 (마감일 기준)...")
        try:
            p_priv = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json', 'prqudoPresentnClosDateBegin': today_str, 'prqudoPresentnClosDateEnd': target_end_day}
            res_priv = requests.get("http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList", params=p_priv, timeout=10).json()
            it_priv = res_priv.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            it_priv = [it_priv] if isinstance(it_priv, dict) else it_priv
            for it in it_priv:
                if any(kw in it.get('othbcNtatNm', '') for kw in KEYWORDS):
                    final_list.append({'출처':'D2B(수의)', '번호':it.get('dcsNo'), '공고명':it.get('othbcNtatNm'), '수요기관':it.get('ornt'), '예산':int(pd.to_numeric(it.get('budgetAmount', 0), errors='coerce') or 0), '지역':'국방부', '마감일':format_date_clean(it.get('prqudoPresentnClosDt')), 'URL':'https://www.d2b.go.kr'})
        except: pass

        # --- 4. 수자원공사 (보내주신 전용 로직 적용) ---
        status_st.info("📡 [PHASE 4] K-water 수색 중...")
        for kw in KWATER_KEYWORDS:
            try:
                res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", params={'serviceKey': SERVICE_KEY, 'searchDt': search_month, 'bidNm': kw, 'numOfRows': '100', '_type': 'json'}, timeout=10).json()
                k_items = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                k_items = [k_items] if isinstance(k_items, dict) else k_items
                for kit in k_items:
                    title = kit.get('tndrPblancNm', '-')
                    if any(k in title for k in KWATER_KEYWORDS):
                        final_list.append({'출처': 'K-water', '번호': kit.get('tndrPbanno', '-'), '공고명': title, '수요기관': '한국수자원공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(kit.get('tndrPblancEnddt')), 'URL': f"https://ebid.kwater.or.kr/wq/index.do?w2xPath=/ui/index.xml&view=/bidpblanc/bidpblancsttus/BIDBD32000002.xml&tndrPbanno={kit.get('tndrPbanno')}"})
            except: continue

        # --- 5. 가스공사 (보내주신 6개월 전용 로직 적용) ---
        status_st.info("📡 [PHASE 5] KOGAS 수색 중...")
        try:
            res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': kogas_start}, timeout=10)
            root_kg = ET.fromstring(res_kg.text)
            for item in root_kg.findall('.//item'):
                title = item.findtext('NOTICE_NAME') or '-'
                if any(kw in title for kw in KOGAS_KEYWORDS):
                    final_list.append({'출처': 'KOGAS', '번호': item.findtext('NOTICE_CODE') or '-', '공고명': title, '수요기관': '한국가스공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(item.findtext('END_DT')), 'URL': "https://bid.kogas.or.kr:9443/supplier/index.jsp"})
        except: pass

        # --- 최종 출력 ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 수색 완료! 총 {len(df)}건의 유효 공고를 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='TOTAL_RADAR')
            st.download_button(label="📥 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_TOTAL_{today_str}.xlsx")
        else:
            st.warning("⚠️ 현재 조건에 맞는 공고가 검색되지 않습니다.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
