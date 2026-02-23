import streamlit as st
import requests
import pandas as pd
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 부장님 커스텀 세팅 (v28.5 기준 유지) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성"]
MUST_PASS = ['경기도', '평택시', '화성시', '서울특별시', '서울', '인천', '전국']
EXCLUDE_LIST = ['충청', '전라', '강원', '경상', '제주', '부산', '대구', '광주', '대전', '울산', '세종', '충북', '충남', '경북', '경남', '전북', '전남']
TARGET_LICENSES = ['6786', '6770', '1226', '1227'] # 이미지 및 지시사항 기반

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v28.7", layout="wide")
st.title("📡 THE RADAR v28.7 (부장님 로직 온전 적용)")

if st.button("🚀 부장님 방식 정밀 수색 시작", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # v28.5 방식 날짜 설정 (4일치)
    s_date = (now - timedelta(days=4)).strftime("%Y%m%d0000")
    e_date = now.strftime("%Y%m%d2359")
    
    status_st = st.empty()
    url_base = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'

    # --- Step 1: v28.5 방식 키워드별 수집 ---
    all_raw = []
    for kw in KEYWORDS:
        status_st.info(f"🔎 키워드 수집 중: {kw}")
        params = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date, 'inqryEndDt': e_date, 'bidNtceNm': kw}
        try:
            res = requests.get(url_base + 'getBidPblancListInfoServcPPSSrch', params=params, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            if items:
                for it in ([items] if isinstance(items, dict) else items):
                    it['searchKeyword'] = kw
                    all_raw.append(it)
        except: pass

    if all_raw:
        df_bids = pd.DataFrame(all_raw).drop_duplicates(subset=['bidNtceNo'])
        
        # --- Step 2: v28.5 방식 상세 분석 및 필터링 ---
        for i, row in df_bids.iterrows():
            b_no = row['bidNtceNo']
            b_ord = str(row.get('bidNtceOrd', '00')).zfill(2)
            status_st.warning(f"⚙️ 상세 필터링 분석 중 ({i+1}/{len(df_bids)}): {b_no}")

            # 🎯 이미지 요청 항목 상세 조회 (v169/v8600 로직)
            reg_val, lic_val = "정보없음", "정보없음"
            is_pass_reg, is_pass_lic = False, False
            
            try:
                # 상세 API 호출 (이미지의 prtcptLmtRgnNm, indstrytyCd 추출용)
                det_res = requests.get(url_base + 'getBidPblancListInfoServcDetail', 
                                     params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=5).json()
                det_item = det_res.get('response', {}).get('body', {}).get('item', {})

                if det_item:
                    # 1. 지역 필터링 (prtcptLmtRgnNm)
                    reg_val = det_item.get('prtcptLmtRgnNm', '전국')
                    if any(ok in reg_val for ok in MUST_PASS) or reg_val == "전국":
                        is_pass_reg = True
                    # 제외 지역에 포함되고 통과 지역에 없으면 탈락
                    if any(no in reg_val for no in EXCLUDE_LIST) and not any(ok in reg_val for ok in MUST_PASS):
                        is_pass_reg = False
                    
                    # 2. 면허 필터링 (indstrytyCd)
                    lic_code = det_item.get('indstrytyCd', '')
                    lic_val = det_item.get('indstrytyNm', '정보없음')
                    if any(c in lic_code for c in TARGET_LICENSES):
                        is_pass_lic = True
                    elif not TARGET_LICENSES: # 면허 필터 없으면 통과
                        is_pass_lic = True
                else:
                    # 상세 정보 없을 경우 v28.5 기본값 적용
                    is_pass_reg, is_pass_lic = True, True
            except:
                is_pass_reg, is_pass_lic = True, True

            # --- Step 3: 최종 통과된 건만 리스트에 추가 ---
            if is_pass_reg and is_pass_lic:
                final_list.append({
                    '키워드': row['searchKeyword'],
                    '공고번호': b_no,
                    '공고명': row['bidNtceNm'],
                    '참가제한지역': reg_val,
                    '업종(면허)': lic_val,
                    '수요기관': row['dminsttNm'],
                    '배정예산': int(pd.to_numeric(row.get('asignBdgtAmt', 0), errors='coerce') or 0),
                    '입찰마감': clean_date_strict(row.get('bidClseDt')),
                    'URL': row.get('bidNtceDtlUrl', '')
                })

        status_st.empty()
        if final_list:
            df_final = pd.DataFrame(final_list)
            st.success(f"🎯 수집 완료! 부장님 필터 통과 공고: {len(df_final)}건")
            st.dataframe(df_final.style.format({'배정예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, index=False)
            st.download_button(label="📥 통합 리포트 다운로드", data=output.getvalue(), file_name=f"나라장터_최종분석_{now.strftime('%m%d_%H%M')}.xlsx")
        else:
            st.warning("⚠️ 조건에 맞는 공고가 없습니다.")
