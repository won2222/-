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
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 기관별 특화 키워드 및 필터
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "임목", "폐가구", "재활용"]
LH_KEYWORDS_REGEX = '폐목재|임목|목재|나무|벌채|뿌리|폐기물|운반|재활용'
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else val

def lh_korean_cleaner(text):
    if not text: return ""
    # CDATA 파쇄 - LH 데이터 수집의 핵심
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

# --- [2] 대시보드 설정 ---
st.set_page_config(page_title="THE RADAR v6200", layout="wide")
st.title("📡 THE RADAR v6200.0")
st.success("🎯 LH 시설공사(Gb:1) 데이터 파싱 규격 보강 및 국방부 통합 완료")

if st.sidebar.button("🔍 7일 정밀 통합 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 🎯 날짜 파라미터 (7일 고정)
    s_date = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=7)).strftime("%Y%m%d")
    
    status_st = st.empty()

    # --- 1. LH (e-Bid) : 부장님 v90.0 시설공사 타격 로직 ---
    status_st.info("📡 [LH포털] 시설공사(Gb:1) 데이터 추출 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        # 🎯 numOfRows를 300으로 조절하여 데이터 누락 방지
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '300', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=15)
        res_lh.encoding = res_lh.apparent_encoding
        
        # 🎯 LH 핵심: XML 루트 강제 생성 및 파싱
        raw_xml = res_lh.text.strip()
        if raw_xml:
            clean_xml = re.sub(r'<\?xml.*\?>', '', raw_xml).strip()
            # <root>로 감싸야 태그 손실 없이 데이터 로드 가능
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
    except Exception as e:
        st.error(f"⚠️ LH 채널 파싱 오류: {e}")

    # --- 2. 국방부 (D2B) : v161/v169 정밀 로직 ---
    status_st.info("📡 [국방부] 일반/수의 통합 예산 엔진 가동...")
    d2b_configs = [
        {'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail', 'c': 'biddocPresentnClosDt'},
        {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail', 'c': 'prqudoPresentnClosDt'}
    ]
    for cfg in d2b_configs:
        try:
            p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}
            if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': s_date, 'prqudoPresentnClosDateEnd': target_end_day})
            res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, headers=HEADERS, timeout=15).json()
            items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            items_d = [items_d] if isinstance(items_d, dict) else items_d
            for it in items_d:
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                if any(kw in bid_nm for kw in KEYWORDS):
                    # 🎯 국방부 핵심: 예산 3중 파싱
                    budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                    p_no = it.get('pblancNo') or it.get('dcsNo')
                    final_list.append({
                        '출처': f"D2B({cfg['t']})", '번호': p_no, '공고명': bid_nm, '수요기관': it.get('ornt'), 
                        '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': "공고참조", 
                        '마감일': format_date_clean(it.get(cfg['c'])), 'URL': 'https://www.d2b.go.kr'
                    })
        except: continue

    # --- [결과 처리] ---
    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
        st.success(f"✅ 작전 완료! LH 포함 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 통합 리포트(Excel) 다운로드", data=output.getvalue(), file_name=f"RADAR_FINAL_{today_str}.xlsx")
    else:
        st.warning("🚨 LH(시설) 및 국방부 채널에 현재 조건과 일치하는 공고가 없습니다.")
