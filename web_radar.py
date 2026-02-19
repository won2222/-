import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
import re
from datetime import datetime, timedelta
import io

# --- [1] LH 전용 정밀 설정 ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def lh_korean_cleaner(text):
    if not text: return ""
    # 성공했던 로직 그대로: CDATA 및 특수문자 제거
    text = re.sub(r'<!\[CDATA\[|\]\]>', '', text)
    return text.strip()

# --- [2] UI 구성 ---
st.set_page_config(page_title="LH ONLY RADAR", layout="wide")
st.title("🚀 LH 전용 정밀 수색 시스템")
st.info("이 모듈은 LH(한국토지주택공사) 시설공사 데이터를 단독으로 정밀 수집합니다.")

# --- [3] 사이드바 설정 ---
st.sidebar.header("📅 수색 기간")
col1, col2 = st.sidebar.columns(2)
with col1:
    s_date = st.sidebar.date_input("시작일", datetime.now() - timedelta(days=14))
with col2:
    e_date = st.sidebar.date_input("종료일", datetime.now() + timedelta(days=7))

st.sidebar.subheader("🔑 핵심 키워드")
default_kw = "폐기물, 운반, 폐목재, 임목, 나무, 벌채, 뿌리, 재활용, 잔재물"
user_kw = st.sidebar.text_area("필터링 단어 (쉼표 구분)", default_kw, height=150)
kw_list = [k.strip() for k in user_kw.split(",") if k.strip()]

# --- [4] 수색 로직 ---
if st.sidebar.button("📡 LH 단독 수색 개시", type="primary"):
    try:
        url = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        s_str = s_date.strftime("%Y%m%d")
        e_str = e_date.strftime("%Y%m%d")
        
        params = {
            'serviceKey': SERVICE_KEY,
            'pageNo': '1',
            'numOfRows': '500',
            'tndrbidRegDtStart': s_str,
            'tndrbidRegDtEnd': e_str,
            'cstrtnJobGb': '1'  # 시설공사 기준
        }

        with st.spinner("LH 서버에서 데이터를 정밀 세척하며 가져오는 중..."):
            # 🎯 성공 포인트 1: 인코딩 명시
            res = requests.get(url, params=params, timeout=25)
            res.encoding = res.apparent_encoding 
            
            # 🎯 성공 포인트 2: XML 찌꺼기 강제 제거
            clean_xml = re.sub(r'<\?xml.*\?>', '', res.text).strip()
            
            if "<resultCode>00</resultCode>" in clean_xml:
                # 🎯 성공 포인트 3: root 강제 래핑
                root = ET.fromstring(f"<root>{clean_xml}</root>")
                final_items = []
                
                for item in root.findall('.//item'):
                    bid_nm = lh_korean_cleaner(item.findtext('bidnmKor', ''))
                    
                    # 🎯 성공 포인트 4: 키워드 매칭
                    if any(kw in bid_nm for kw in kw_list):
                        final_items.append({
                            '공고번호': item.findtext('bidNum'),
                            '공고명': bid_nm,
                            '등록일': item.findtext('tndrbidRegDt'),
                            '개찰일시': item.findtext('openDtm'),
                            '예산(기초금액)': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce')),
                            '상세링크': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                        })

                if final_items:
                    df = pd.DataFrame(final_items).drop_duplicates(subset=['공고번호'])
                    st.success(f"🎯 LH 공고 {len(df)}건을 성공적으로 포착했습니다!")
                    
                    # 결과 테이블 (링크 클릭 가능하게 설정)
                    st.dataframe(
                        df.style.format({'예산(기초금액)': '{:,}원'}),
                        use_container_width=True,
                        column_config={"상세링크": st.column_config.LinkColumn()}
                    )
                    
                    # 엑셀 다운로드
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, index=False)
                    st.download_button("📥 LH 결과 엑셀 저장", data=output.getvalue(), file_name=f"LH_SEARCH_{s_str}.xlsx")
                else:
                    st.warning("⚠️ 해당 기간 내 키워드와 일치하는 LH 공고가 없습니다.")
            else:
                st.error("❌ LH 서버 응답 오류 (인증키 또는 파라미터를 확인하세요)")
                st.code(clean_xml[:500])

    except Exception as e:
        st.error(f"🚨 시스템 충돌 발생: {e}")
