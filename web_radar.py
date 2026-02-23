import streamlit as st
import requests
import pandas as pd
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 부장님 정예 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성"]

def clean_date(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v9200", layout="wide")
st.title("📡 THE RADAR v9200.0 (매뉴얼 212P 상세항목 직결)")

if st.button("🚀 매뉴얼 규격 데이터 수집 시작", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 최근 4일치 데이터 기준
    s_date = (now - timedelta(days=4)).strftime("%Y%m%d0000")
    e_date = now.strftime("%Y%m%d2359")
    
    status_st = st.empty()
    url_base = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'

    # --- 1단계: 키워드 서치 (용역공고 목록) ---
    all_raw = []
    for kw in KEYWORDS:
        status_st.info(f"🔎 1단계: 키워드 '{kw}' 목록 수집 중...")
        params = {
            'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json',
            'inqryDiv': '1', 'inqryBgnDt': s_date, 'inqryEndDt': e_date, 'bidNtceNm': kw
        }
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
        
        # --- 2단계: 매뉴얼 212P 상세조회 (지역/업종 무조건 추출) ---
        for i, row in df_bids.iterrows():
            b_no = row['bidNtceNo']
            b_ord = str(row.get('bidNtceOrd', '00')).zfill(2)
            status_st.warning(f"⚙️ 2단계: 공고 {b_no} 상세 매칭 중... ({i+1}/{len(df_bids)})")

            # 초기값 설정
            reg_val = "정보없음"
            lic_cd = "-"
            lic_nm = "-"
            
            try:
                # 매뉴얼 규격 상세 API 호출
                det_url = url_base + 'getBidPblancListInfoServcDetail'
                det_res = requests.get(det_url, params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=5).json()
                
                # 매뉴얼 규격: response > body > item (객체형태)
                det_item = det_res.get('response', {}).get('body', {}).get('item', {})

                if det_item:
                    # 🎯 매뉴얼 214P: 참가제한지역명 (prtcptLmtRgnNm)
                    reg_val = det_item.get('prtcptLmtRgnNm') or "전국(제한없음)"
                    
                    # 🎯 매뉴얼 215P: 업종코드 (indstrytyCd) 및 명칭 (indstrytyNm)
                    lic_cd = det_item.get('indstrytyCd') or "-"
                    lic_nm = det_item.get('indstrytyNm') or "-"
            except:
                pass

            # 필터링 없이 무조건 리스트 추가
            final_list.append({
                '키워드': row['searchKeyword'],
                '공고번호': b_no,
                '공고명': row['bidNtceNm'],
                '참가제한지역명': reg_val,
                '업종코드': lic_cd,
                '업종명': lic_nm,
                '수요기관': row['dminsttNm'],
                '배정예산': int(pd.to_numeric(row.get('asignBdgtAmt', 0), errors='coerce') or 0),
                '마감일시': clean_date(row.get('bidClseDt')),
                '공고URL': row.get('bidNtceDtlUrl', '')
            })

        status_st.empty()
        if final_list:
            df_final = pd.DataFrame(final_list).sort_values(by=['마감일시'])
            st.success(f"✅ 매뉴얼 규격 수집 완료! 총 {len(df_final)}건 분석됨")
            st.dataframe(df_final.style.format({'배정예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, index=False)
            st.download_button(label="📥 데이터 리포트 다운로드", data=output.getvalue(), file_name=f"G2B_MANUAL_DATA_{now.strftime('%m%d')}.xlsx")
        else:
            st.warning("⚠️ 검색된 원본 데이터가 없습니다.")
