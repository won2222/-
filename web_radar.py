import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import io
import re

# --- [1] 부장님 정예 설정 (v169 기반) ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "잔재물", "매립", "재활용"]

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v5500", layout="wide")
st.title("📡 THE RADAR v5500.0")
st.error("🚀 LH 전용 CDATA 파쇄기 가동: 숨겨진 LH 데이터를 강제로 추출합니다.")

if st.sidebar.button("🔍 LH & 국방부 정밀 수색", type="primary"):
    final_list = []
    now = datetime.now()
    
    # 🎯 LH 전용 8자리 날짜 언어 (부장님 v169 방식)
    lh_start = (now - timedelta(days=15)).strftime("%Y%m%d")
    lh_end = now.strftime("%Y%m%d")
    
    status_st = st.empty()

    # --- 1. LH (e-Bid) : CDATA 파쇄 수색 ---
    status_st.info("📡 [LH포털] CDATA 장벽 파쇄 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        params_lh = {
            'serviceKey': SERVICE_KEY, 
            'numOfRows': '500', 
            'tndrbidRegDtStart': lh_start, 
            'tndrbidRegDtEnd': lh_end, 
            'cstrtnJobGb': '1'
        }
        
        # LH 서버는 응답이 XML이므로 문자열로 먼저 받습니다.
        res_lh = requests.get(url_lh, params=params_lh, timeout=15)
        res_lh.encoding = 'utf-8' # 한글 깨짐 방지
        
        # 🎯 [핵심] 부장님 v169.0 필살기: CDATA 강제 제거
        raw_xml = res_lh.text
        clean_xml = re.sub(r'<!\[CDATA\[|\]\]>', '', raw_xml) # CDATA 껍데기 파쇄
        
        # 파쇄된 텍스트를 다시 XML 구조로 해석
        root = ET.fromstring(clean_xml)
        items = root.findall('.//item')
        
        for item in items:
            # 껍데기가 벗겨진 깨끗한 공고명 추출
            bid_nm = item.findtext('bidnmKor', '').strip()
            
            if any(kw in bid_nm for kw in KEYWORDS):
                final_list.append({
                    '출처': 'LH',
                    '번호': item.findtext('bidNum'),
                    '공고명': bid_nm,
                    '수요기관': '한국토지주택공사',
                    '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                    '지역': '전국(상세확인)',
                    '마감일': clean_date_strict(item.findtext('openDtm')),
                    'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                })
                st.write(f"✅ LH 포착: {bid_nm[:30]}...")
    except Exception as e:
        st.warning(f"⚠️ LH 서버 통신 지연 (직접 접속 권장): {e}")

    # --- 2. 국방부 (D2B) : 성공 로직 유지 ---
    status_st.info("📡 [국방부] 데이터 수집 중...")
    # (국방부 수집 로직은 잘 되니까 그대로 수행)
    try:
        url_d = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
        res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '200', '_type': 'json'}, timeout=15).json()
        items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        for it in ([items_d] if isinstance(items_d, dict) else items_d):
            bid_nm = it.get('bidNm', '')
            if any(kw in bid_nm for kw in KEYWORDS):
                final_list.append({
                    '출처': 'D2B(일반)', '번호': it.get('pblancNo'), '공고명': bid_nm, '수요기관': it.get('ornt'),
                    '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or 0)), '지역': '상세참조',
                    '마감일': clean_date_strict(it.get('biddocPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'
                })
    except: pass

    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by='마감일')
        st.success(f"✅ 수색 완료! LH 포함 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
    else:
        st.warning("🚨 모든 장벽을 깼으나 현재 진행 중인 LH/국방부 공고가 없습니다.")
