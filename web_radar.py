import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 커스텀 설정 (부장님 오더 반영) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 통합 키워드 세트 (18종 확장)
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
            "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]

# 기관별 정밀 키워드 (파일 로직)
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

# 지역 필터링
MUST_PASS = ['경기도', '평택시', '화성시', '서울특별시', '서울', '인천', '전국']

def clean_date(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 웹 인터페이스 구성 ---
st.set_page_config(page_title="THE RADAR v450", layout="wide")
st.title("📡 THE RADAR: 전국 통합 폐기물 레이더")
st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE SYSTEM")

# 사이드바: 기간 설정 기능 (살려두었습니다)
st.sidebar.header("🕹️ 수색 범위 설정")
search_days = st.sidebar.slider("조회 기간 (오늘 기준 과거/미래)", 1, 30, 7)
kogas_months = st.sidebar.number_input("가스공사 과거 조회 (개월)", 1, 12, 6)

if st.sidebar.button("🚀 전 기관 통합 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 상단 조회 시각 표시
    fetch_time = now.strftime("%Y-%m-%d %H:%M:%S")
    st.subheader(f"⏱️ 레이더 가동 시각: :blue[{fetch_time}]")
    
    # 날짜 계산
    s_date_api = (now - timedelta(days=search_days)).strftime("%Y%m%d")
    today_api = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=search_days)).strftime("%Y%m%d")
    kogas_start = (now - timedelta(days=kogas_months*30)).strftime("%Y%m%d")
    search_month = now.strftime('%Y%m')

    status_st = st.empty()
    prog = st.progress(0)

    try:
        # --- 1. 나라장터 (G2B) ---
        status_st.info("📡 [1/5] 나라장터(G2B) 수색 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / 100)
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 
                     'inqryBgnDt': s_date_api+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                for it in ([items] if isinstance(items, dict) else items):
                    final_list.append({
                        '출처': '나라장터', '번호': it.get('bidNtceNo'), '공고명': it.get('bidNtceNm'),
                        '수요기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0),
                        '마감일시': clean_date(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')
                    })
            except: continue

        # --- 2. LH (공사 채널) ---
        status_st.info("📡 [2/5] LH 공사 채널 수색 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date_api, 'tndrbidRegDtEnd': today_api, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, timeout=10)
            res_lh.encoding = res_lh.apparent_encoding
            root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text).strip())
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    b_no = item.findtext('bidNum')
                    final_list.append({
                        '출처': 'LH', '번호': b_no, '공고명': bid_nm, '수요기관': '한국토지주택공사',
                        '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0),
                        '마감일시': clean_date(item.findtext('openDtm')), 
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}"
                    })
        except: pass

        # --- 3. 국방부 (D2B) ---
        status_st.info("📡 [3/5] 국방부(D2B) 수색 중 (마감일 기준)...")
        try:
            p_d2b = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json', 
                     'prqudoPresentnClosDateBegin': today_api, 'prqudoPresentnClosDateEnd': target_end_day}
            res_d = requests.get("http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList", params=p_d2b, timeout=10).json()
            it_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for it in ([it_d] if isinstance(it_d, dict) else it_d):
                if any(kw in it.get('othbcNtatNm', '') for kw in KEYWORDS):
                    final_list.append({
                        '출처': '국방부', '번호': it.get('dcsNo'), '공고명': it.get('othbcNtatNm'),
                        '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(it.get('budgetAmount', 0), errors='coerce') or 0),
                        '마감일시': clean_date(it.get('prqudoPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'
                    })
        except: pass

        # --- 4. 수자원공사 (파일 로직 적용) ---
        status_st.info("📡 [4/5] K-water 정밀 필터링 중...")
        for kw in KWATER_KEYWORDS:
            try:
                res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", 
                                     params={'serviceKey': SERVICE_KEY, 'searchDt': search_month, 'bidNm': kw, '_type': 'json'}, timeout=10).json()
                items_k = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for kit in ([items_k] if isinstance(items_k, dict) else items_k):
                    if any(k in kit.get('tndrPblancNm', '') for k in KWATER_KEYWORDS):
                        final_list.append({
                            '출처': '수자원', '번호': kit.get('tndrPbanno'), '공고명': kit.get('tndrPblancNm'),
                            '수요기관': '한국수자원공사', '예산': 0, '마감일시': clean_date(kit.get('tndrPblancEnddt')), 
                            'URL': "https://ebid.kwater.or.kr"
                        })
            except: continue

        # --- 5. 가스공사 (파일 로직 적용) ---
        status_st.info("📡 [5/5] KOGAS 6개월 정밀 수색 중...")
        try:
            res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", 
                                  params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': kogas_start}, timeout=15)
            root_kg = ET.fromstring(res_kg.text)
            for item in root_kg.findall('.//item'):
                title = item.findtext('NOTICE_NAME') or '-'
                if any(kw in title for kw in KOGAS_KEYWORDS):
                    final_list.append({
                        '출처': '가스공사', '번호': item.findtext('NOTICE_CODE'), '공고명': title,
                        '수요기관': '한국가스공사', '예산': 0, '마감일시': clean_date(item.findtext('END_DT')), 
                        'URL': "https://bid.kogas.or.kr:9443/supplier/index.jsp"
                    })
        except: pass

        # --- 최종 결과 처리 ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일시'])
            
            # 요약 지표 표시
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("총 공고", f"{len(df)}건")
            c2.metric("마감임박", f"{len(df[df['마감일시'] <= today_api])}건")
            
            st.write("### 🔍 통합 수색 결과 리스트")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            # 엑셀 다운로드
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='RADAR')
            st.download_button(label="📥 통합 리포트(Excel) 다운로드", data=output.getvalue(), file_name=f"RADAR_{today_api}.xlsx")
        else:
            st.warning("⚠️ 선택하신 조건에 맞는 공고가 현재 없습니다.")
            
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
