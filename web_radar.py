import streamlit as st
import requests
import pandas as pd
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 부장님 정예 커스텀 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 수집 대상 키워드 (v28.5 기준)
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성"]

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v9000", layout="wide")
st.title("📡 THE RADAR v9000.0 (지역/업종 무조건 수집)")

if st.button("🚀 2단계 상세 수색 시작 (필터 없음)", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 최근 4일치 데이터 수집
    s_date = (now - timedelta(days=4)).strftime("%Y%m%d0000")
    e_date = now.strftime("%Y%m%d2359")
    
    status_st = st.empty()
    url_base = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'

    # --- 1단계: 키워드로 공고 목록 서치 ---
    all_raw = []
    for kw in KEYWORDS:
        status_st.info(f"🔎 1단계: 키워드 '{kw}' 검색 중...")
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
        # 공고번호 기준으로 중복 제거
        df_bids = pd.DataFrame(all_raw).drop_duplicates(subset=['bidNtceNo'])
        
        # --- 2단계: 공고번호 대입하여 이미지 속 상세 정보(지역/업종) 무조건 추출 ---
        for i, row in df_bids.iterrows():
            b_no = row['bidNtceNo']
            b_ord = str(row.get('bidNtceOrd', '00')).zfill(2)
            status_st.warning(f"⚙️ 2단계: 공고번호({b_no}) 상세 데이터 추출 중... ({i+1}/{len(df_bids)})")

            # 이미지 항목 초기값 설정
            reg_val = "확인불가"
            lic_code = "확인불가"
            lic_name = "확인불가"
            
            try:
                # [부장님 이미지 항목] 용역공고 상세조회 API 호출
                det_res = requests.get(url_base + 'getBidPblancListInfoServcDetail', 
                                     params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=5).json()
                det_item = det_res.get('response', {}).get('body', {}).get('item', {})

                if det_item:
                    # 🎯 이미지 속 prtcptLmtRgnNm (참가제한지역명) 추출
                    reg_val = det_item.get('prtcptLmtRgnNm', '전국(제한없음)')
                    
                    # 🎯 이미지 속 indstrytyCd (업종코드) 및 indstrytyNm (업종명) 추출
                    lic_code = det_item.get('indstrytyCd', '-')
                    lic_name = det_item.get('indstrytyNm', '-')
            except:
                pass

            # 필터 없이 모든 검색 결과 리스트에 추가
            final_list.append({
                '키워드': row['searchKeyword'],
                '공고번호': b_no,
                '공고명': row['bidNtceNm'],
                '참가제한지역명(prtcptLmtRgnNm)': reg_val,
                '업종코드(indstrytyCd)': lic_code,
                '업종명(indstrytyNm)': lic_name,
                '수요기관': row['dminsttNm'],
                '배정예산': int(pd.to_numeric(row.get('asignBdgtAmt', 0), errors='coerce') or 0),
                '마감일시': clean_date_strict(row.get('bidClseDt')),
                '상세URL': row.get('bidNtceDtlUrl', '')
            })

        status_st.empty()
        if final_list:
            df_final = pd.DataFrame(final_list)
            # 마감일 순 정렬
            df_final = df_final.sort_values(by=['마감일시'])
            
            st.success(f"✅ 수집 완료! 총 {len(df_final)}건의 지역 및 업종 정보를 확보했습니다.")
            st.dataframe(df_final.style.format({'배정예산': '{:,}원'}), use_container_width=True)
            
            # 엑셀 다운로드
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, index=False)
            st.download_button(label="📥 수집 리포트 다운로드", data=output.getvalue(), file_name=f"G2B_FULL_DATA_{now.strftime('%m%d')}.xlsx")
        else:
            st.warning("⚠️ 검색된 공고가 없습니다.")
