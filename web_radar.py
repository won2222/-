import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import io
import re

# --- [1] LH Open API 가이드 명세 기반 설정 ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
LH_API_URL = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"

# 부장님 선호 키워드
KEYWORDS_REGEX = '폐기물|운반|폐목재|폐합성수지|잔재물|가연성|낙엽|식물성|부유물|임목|재활용'

def lh_korean_cleaner(text):
    if not text: return ""
    # 가이드 예제에 포함된 CDATA 태그 제거 [cite: 28]
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

def format_date(val):
    if not val: return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else val

# --- [2] 대시보드 인터페이스 ---
st.set_page_config(page_title="THE RADAR v6100", layout="wide")
st.title("📡 THE RADAR v6100.0")
st.success("🎯 LH Open API 활용가이드 명세(v1.4) 필수 파라미터 적용 완료")

if st.sidebar.button("🚀 LH 시설공사 명세서 규격 수색", type="primary"):
    final_list = []
    now = datetime.now()
    
    # 🎯 가이드 명세에 따른 날짜 설정 (8자리 YYYYMMDD) [cite: 21]
    # 시작일: 7일 전, 종료일: 오늘
    start_dt = (now - timedelta(days=7)).strftime("%Y%m%d")
    end_dt = now.strftime("%Y%m%d")
    
    status_st = st.empty()
    status_st.info(f"📡 LH 서버에 명세 규격(날짜: {start_dt}~{end_dt})으로 접근 중...")

    try:
        # 🎯 가이드 [요청 메시지 명세] 반영 [cite: 21]
        # 공고번호(bidNum)를 제외한 필수 항목(1) 및 날짜쌍(0) 구성
        params = {
            'serviceKey': SERVICE_KEY,     # 필수
            'numOfRows': '500',            # 필수
            'pageNo': '1',                 # 필수
            'tndrbidRegDtStart': start_dt, # 날짜쌍(필수조건)
            'tndrbidRegDtEnd': end_dt,     # 날짜쌍(필수조건)
            'cstrtnJobGb': '1'             # 부장님 지시: 시설공사 고정
        }
        
        res = requests.get(LH_API_URL, params=params, timeout=20)
        res.encoding = 'utf-8' # 가이드 권장 인코딩
        
        # XML 루트 및 CDATA 처리 [cite: 28]
        clean_xml = re.sub(r'<\?xml.*\?>', '', res.text).strip()
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        
        # resultCode '00'(정상) 확인 [cite: 25, 30]
        if root.findtext('.//resultCode') == "00":
            items = root.findall('.//item')
            for item in items:
                # 가이드 응답 필드 매칭 [cite: 25]
                raw_nm = item.findtext('bidnmKor', '')
                clean_nm = lh_korean_cleaner(raw_nm)
                
                if re.search(KEYWORDS_REGEX, clean_nm):
                    final_list.append({
                        '출처': 'LH(시설)',
                        '공고번호': item.findtext('bidNum'),    # bidNum [cite: 25]
                        '공고명': clean_nm,                     # bidnmKor [cite: 25]
                        '수요기관': '한국토지주택공사',
                        '기초금액': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), # fdmtlAmt [cite: 25]
                        '개찰일시': format_date(item.findtext('openDtm')), # openDtm [cite: 25]
                        '진행상태': item.findtext('bidProgrsStatus')      # bidProgrsStatus [cite: 25]
                    })
            
            if final_list:
                df = pd.DataFrame(final_list).sort_values(by='개찰일시')
                st.success(f"✅ 수색 성공! {len(df)}건의 LH 시설공사 공고를 찾았습니다.")
                st.dataframe(df.style.format({'기초금액': '{:,}원'}), use_container_width=True)
            else:
                st.warning("⚠️ 해당 기간 내에 키워드와 일치하는 LH 공고가 없습니다.")
        else:
            err_msg = root.findtext('.//resultMsg')
            st.error(f"❌ LH 서버 응답 오류: {err_msg}")

    except Exception as e:
        st.error(f"🚨 시스템 오류 발생: {e}")
