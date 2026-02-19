import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import re
from datetime import datetime, timedelta

# --- [1] LH 전용 세척 함수 ---
def lh_cleaner(text):
    if not text: return ""
    # CDATA 및 특수문자 제거 (부장님 성공 로직)
    text = re.sub(r'<!\[CDATA\[|\]\]>', '', text)
    return text.strip()

# --- [2] UI 레이아웃 ---
st.set_page_config(page_title="LH ONLY TEST", layout="wide")
st.title("🚀 LH 시설공사 정밀 테스트")
st.markdown("---")

# 사이드바 설정
st.sidebar.header("🕹️ 수색 범위 설정")
s_date = st.sidebar.date_input("수색 시작일", datetime.now() - timedelta(days=14))
e_date = st.sidebar.date_input("수색 종료일", datetime.now() + timedelta(days=7))

# 부장님 고정 키워드
TARGET_KW = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "임목", "폐가구", "대형"]

if st.sidebar.button("📡 LH 서버 집중 수색", type="primary"):
    SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
    HEADERS = {'User-Agent': 'Mozilla/5.0'}
    
    s_str = s_date.strftime("%Y%m%d")
    e_str = e_date.strftime("%Y%m%d")
    
    status = st.empty()
    status.info(f"⏳ LH 서버에 접속 중입니다... (기간: {s_str} ~ {e_str})")
    
    try:
        url = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        params = {
            'serviceKey': SERVICE_KEY,
            'pageNo': '1',
            'numOfRows': '500',
            'tndrbidRegDtStart': s_str,
            'tndrbidRegDtEnd': e_str,
            'cstrtnJobGb': '1'  # 시설공사
        }

        # 🎯 핵심: 타임아웃을 30초로 늘려 응답을 강제로 기다림
        res = requests.get(url, params=params, headers=HEADERS, timeout=30)
        res.encoding = res.apparent_encoding
        
        # 서버 응답 원문 확인 (디버깅용)
        raw_data = res.text.strip()
        
        if not raw_data:
            st.error("🚨 LH 서버로부터 아무런 응답을 받지 못했습니다. (Empty Response)")
        elif "<resultCode>00</resultCode>" in raw_data:
            clean_xml = re.sub(r'<\?xml.*\?>', '', raw_data).strip()
            # root로 감싸기 (파싱 안정성)
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            items = root.findall('.//item')
            
            final_data = []
            for item in items:
                bid_nm = lh_cleaner(item.findtext('bidnmKor', ''))
                # 키워드 매칭
                if any(kw in bid_nm for kw in TARGET_KW):
                    final_data.append({
                        '번호': item.findtext('bidNum'),
                        '공고명': bid_nm,
                        '기초금액': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                        '등록일': item.findtext('tndrbidRegDt'),
                        '개찰일시': item.findtext('openDtm'),
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
            
            if final_data:
                status.success(f"✅ 총 {len(final_data)}건의 LH 공고를 찾아냈습니다!")
                df = pd.DataFrame(final_data)
                st.dataframe(df.style.format({'기초금액': '{:,}원'}), use_container_width=True)
            else:
                status.warning("⚠️ LH 서버에 접속했으나, 해당 기간 내 키워드와 일치하는 공고가 없습니다.")
                with st.expander("서버 응답 원문 보기"):
                    st.code(raw_data[:1000])
        else:
            st.error("❌ LH 서버 응답 오류 (인증키 또는 날짜 포맷 확인 필요)")
            st.code(raw_data[:500])
            
    except requests.exceptions.Timeout:
        st.error("🚨 LH 서버 응답 시간이 너무 길어 연결이 끊겼습니다. (Timeout)")
    except Exception as e:
        st.error(f"🚨 시스템 오류 발생: {e}")
