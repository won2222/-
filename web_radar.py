import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import re
from datetime import datetime, timedelta

# --- [1] LH 전용 설정 ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def lh_korean_cleaner(text):
    if not text: return ""
    # CDATA 및 공백 제거
    text = re.sub(r'<!\[CDATA\[|\]\]>', '', text)
    return text.strip()

# --- [2] UI 레이아웃 ---
st.set_page_config(page_title="LH TEST ONLY", layout="wide")
st.title("🚀 LH 정밀 타격 테스트")
st.info("다른 기관을 배제하고 LH 시설공사 데이터만 정밀하게 긁어옵니다.")

# 검색 기간 설정 (기본 7일)
col1, col2 = st.columns(2)
with col1:
    s_date = st.date_input("수색 시작일", datetime.now() - timedelta(days=7))
with col2:
    e_date = st.date_input("수색 종료일", datetime.now())

target_kw = st.text_input("필터 키워드 (쉼표로 구분)", "폐기물, 운반, 폐목재, 임목, 나무, 벌채, 뿌리, 재활용")

if st.button("📡 LH 서버 접속 및 수색 개시", type="primary"):
    try:
        url = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        
        # 날짜 포맷 변환
        s_str = s_date.strftime("%Y%m%d")
        e_str = e_date.strftime("%Y%m%d")
        
        params = {
            'serviceKey': SERVICE_KEY,
            'pageNo': '1',
            'numOfRows': '500',
            'tndrbidRegDtStart': s_str,
            'tndrbidRegDtEnd': e_str,
            'cstrtnJobGb': '1' # 시설공사 고정
        }

        with st.spinner("LH 서버에서 데이터를 청소하며 가져오는 중..."):
            res = requests.get(url, params=params, timeout=20)
            res.encoding = res.apparent_encoding # 🎯 한글 깨짐 방지 핵심
            raw_text = res.text

            # 🎯 XML 찌꺼기 강제 청소
            clean_xml = re.sub(r'<\?xml.*\?>', '', raw_text).strip()
            
            if "<resultCode>00</resultCode>" in clean_xml:
                # 🎯 파싱 에러 방지를 위해 root로 감싸기
                root = ET.fromstring(f"<root>{clean_xml}</root>")
                items = []
                
                kw_list = [k.strip() for k in target_kw.split(",")]
                
                for item in root.findall('.//item'):
                    bid_nm = lh_korean_cleaner(item.findtext('bidnmKor'))
                    
                    # 키워드 매칭 검사
                    if any(kw in bid_nm for kw in kw_list):
                        items.append({
                            '공고번호': item.findtext('bidNum'),
                            '공고명': bid_nm,
                            '등록일': item.findtext('tndrbidRegDt'),
                            '개찰일시': item.findtext('openDtm'),
                            '기초금액': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce')),
                            'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                        })

                if items:
                    df = pd.DataFrame(items)
                    st.success(f"🎯 LH 서버에서 관련 공고 {len(df)}건을 포착했습니다!")
                    st.dataframe(df, use_container_width=True)
                    
                    # 엑셀 다운로드 기능
                    output = pd.ExcelWriter("LH_TEST_RESULT.xlsx", engine='xlsxwriter')
                    df.to_excel(output, index=False)
                    output.close()
                else:
                    st.warning("✅ LH 서버에 접속했으나 해당 기간/키워드에 맞는 공고가 없습니다.")
                    st.write("---")
                    st.write("💡 **참고 (전체 응답 요약):**")
                    st.code(clean_xml[:500] + "...") # 응답 확인용
            else:
                st.error("❌ LH 서버 응답 오류 (ResultCode가 00이 아닙니다)")
                st.code(clean_xml[:500])

    except Exception as e:
        st.error(f"🚨 테스트 중 시스템 오류 발생: {e}")
