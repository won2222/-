import streamlit as st
import requests
import pandas as pd
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 설정 (매뉴얼 기반) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성"]

def clean_date(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 ---
st.set_page_config(page_title="THE RADAR v9100", layout="wide")
st.title("📡 THE RADAR v9100.0 (매뉴얼 212P 정밀 수집)")

if st.button("🚀 매뉴얼 규격 2단계 수색 시작", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 최근 4일치 조회
    s_date = (now - timedelta(days=4)).strftime("%Y%m%d0000")
    e_date = now.strftime("%Y%m%d2359")
    
    status_st = st.empty()
    # 매뉴얼 상의 서비스 엔드포인트
    url_base = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'

    # --- 1단계: 용역입찰공고 목록 서치 ---
    all_raw = []
    for kw in KEYWORDS:
        status_st.info(f"🔎 1단계: '{kw}' 공고 목록 수집 중...")
        params = {
            'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json',
            'inqryDiv': '1', 'inqryBgnDt': s_date, 'inqryEndDt': e_date, 'bidNtceNm': kw
        }
        try:
            # 매뉴얼 212p 부근 용역공고 조회 서비스
            res = requests.get(url_base + 'getBidPblancListInfoServcPPSSrch', params=params, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            if items:
                for it in ([items] if isinstance(items, dict) else items):
                    it['searchKeyword'] = kw
                    all_raw.append(it)
        except: pass

    if all_raw:
        df_bids = pd.DataFrame(all_raw).drop_duplicates(subset=['bidNtceNo'])
        
        # --- 2단계: 공고번호 대입 상세 데이터(지역/업종) 무조건 추출 ---
        for i, row in df_bids.iterrows():
            b_no = row['bidNtceNo']
            b_ord = str(row.get('bidNtceOrd', '00')).zfill(2)
            status_st.warning(f"⚙️ 2단계 상세조회 ({i+1}/{len(df_bids)}): {b_no}")

            # 매뉴얼 항목 초기화
            rgn_nm = "미제한/전국"
            ind_cd = "-"
            ind_nm = "-"
            
            try:
                # [매뉴얼 규격 상세조회 호출]
                det_url = url_base + 'getBidPblancListInfoServcDetail'
                det_res = requests.get(det_url, params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=5).json()
                det_body = det_res.get('response', {}).get('body', {})
                
                # 매뉴얼 212P 이후 상세 항목 매핑
                if det_body and 'item' in det_body:
                    det_item = det_body['item']
                    # 참가제한지역명 (prtcptLmtRgnNm)
                    rgn_nm = det_item.get('prtcptLmtRgnNm') or "전국(제한없음)"
                    # 업종코드 (indstrytyCd) 및 업종명 (indstrytyNm)
                    ind_cd = det_item.get('indstrytyCd') or "-"
                    ind_nm = det_item.get('indstrytyNm') or "-"
            except:
                pass

            # 필터링 없이 모든 결과 데이터 구성
            final_list.append({
                '키워드': row['searchKeyword'],
                '공고번호': b_no,
                '공고명': row['bidNtceNm'],
                '참가제한지역명': rgn_nm,
                '업종코드': ind_cd,
                '업종명': ind_nm,
                '수요기관': row['dminsttNm'],
                '예산': int(pd.to_numeric(row.get('asignBdgtAmt', 0), errors='coerce') or 0),
                '마감일시': clean_date(row.get('bidClseDt')),
                '상세URL': row.get('bidNtceDtlUrl', '')
            })

        status_st.empty()
        if final_list:
            df_final = pd.DataFrame(final_list).sort_values(by=['마감일시'])
            st.success(f"✅ 매뉴얼 규격 수집 완료! (총 {len(df_final)}건)")
            st.dataframe(df_final.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, index=False)
            st.download_button(label="📥 데이터 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_MANUAL_V9100_{now.strftime('%m%d')}.xlsx")
        else:
            st.warning("⚠️ 검색된 공고가 없습니다.")
