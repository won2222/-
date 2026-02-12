import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 부장님 정예 커스텀 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# [파일참고] 통합 키워드 세트 (18종)
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

# [파일참고] 지역 필터
MUST_PASS = ['경기도', '평택시', '화성시', '서울특별시', '서울', '인천', '전국']

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 웹 페이지 레이아웃 ---
st.set_page_config(page_title="THE RADAR v400", layout="wide")
st.title("📡 THE RADAR")
st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE SYSTEM (WEB MODE)")
st.divider()

# 사이드바 설정
st.sidebar.header("🕹️ 수색 설정")
days_range = st.sidebar.slider("공고일 조회 범위(일)", 1, 14, 7)

if st.sidebar.button("🚀 전 기관 통합 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 날짜 파라미터 세팅
    s_date_api = (now - timedelta(days=days_range)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m')
    kogas_start = (now - timedelta(days=180)).strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=7)).strftime("%Y%m%d")

    status_st = st.empty()
    prog = st.progress(0)

    try:
        # --- PHASE 1. 나라장터 (G2B) ---
        status_st.info("📡 [1단계] 나라장터(G2B) 수색 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / 100)
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date_api+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                for it in ([items] if isinstance(items, dict) else items):
                    if "전자입찰" not in it.get('bidMethdNm', ''): continue
                    final_list.append({'출처':'나라장터', '번호':it.get('bidNtceNo'), '공고명':it.get('bidNtceNm'), '수요기관':it.get('dminsttNm'), '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '마감일':clean_date_strict(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
            except: continue

        # --- PHASE 2. LH (공사 채널 고정) ---
        status_st.info("📡 [2단계] LH 공사 채널 수색 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date_api, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=10)
            res_lh.encoding = res_lh.apparent_encoding
            root = ET.fromstring(f"<root>{re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()}</root>")
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    final_list.append({'출처':'LH', '번호':item.findtext('bidNum'), '공고명':bid_nm, '수요기관':'한국토지주택공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), '마감일':clean_date_strict(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"})
        except: pass

        # --- PHASE 3. 국방부 (마감일 기준) ---
        status_st.info("📡 [3단계] 국방부(D2B) 수색 중 (마감일 기준)...")
        try:
            p_priv = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json', 'prqudoPresentnClosDateBegin': today_str, 'prqudoPresentnClosDateEnd': target_end_day}
            res_priv = requests.get("http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList", params=p_priv, timeout=10).json()
            it_priv = res_priv.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for it in ([it_priv] if isinstance(it_priv, dict) else it_priv):
                if any(kw in it.get('othbcNtatNm', '') for kw in KEYWORDS):
                    final_list.append({'출처':'국방부', '번호':it.get('dcsNo'), '공고명':it.get('othbcNtatNm'), '수요기관':it.get('ornt'), '예산':int(pd.to_numeric(it.get('budgetAmount', 0), errors='coerce') or 0), '마감일':clean_date_strict(it.get('prqudoPresentnClosDt')), 'URL':'https://www.d2b.go.kr'})
        except: pass

        # --- PHASE 4. 수자원공사 (파일 전용 로직) ---
        status_st.info("📡 [4단계] K-water 수색 중...")
        for kw in KWATER_KEYWORDS:
            try:
                res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", params={'serviceKey': SERVICE_KEY, 'searchDt': search_month, 'bidNm': kw, '_type': 'json'}, timeout=10).json()
                items_k = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for kit in ([items_k] if isinstance(items_k, dict) else items_k):
                    if any(k in kit.get('tndrPblancNm', '') for k in KWATER_KEYWORDS):
                        final_list.append({'출처': '수자원', '번호': kit.get('tndrPbanno'), '공고명': kit.get('tndrPblancNm'), '수요기관': '수자원공사', '예산': 0, '마감일': clean_date_strict(kit.get('tndrPblancEnddt')), 'URL': "https://ebid.kwater.or.kr"})
            except: continue

        # --- PHASE 5. 가스공사 (파일 6개월 로직) ---
        status_st.info("📡 [5단계] KOGAS 수색 중...")
        try:
            res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': kogas_start}, timeout=10)
            root_kg = ET.fromstring(res_kg.text)
            for item in root_kg.findall('.//item'):
                title = item.findtext('NOTICE_NAME') or '-'
                if any(kw in title for kw in KOGAS_KEYWORDS):
                    final_list.append({'출처': '가스공사', '번호': item.findtext('NOTICE_CODE'), '공고명': title, '수요기관': '가스공사', '예산': 0, '마감일': clean_date_strict(item.findtext('END_DT')), 'URL': "https://bid.kogas.or.kr:9443/supplier/index.jsp"})
        except: pass

        # --- 최종 출력 ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            
            # 요약 지표
            counts = df['출처'].value_counts()
            cols = st.columns(len(counts))
            for idx, (name, count) in enumerate(counts.items()):
                cols[idx].metric(name, f"{count}건")
            
            st.success(f"✅ 작전 성공! 총 {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            # 엑셀 다운로드
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='RADAR')
            st.download_button(label="📥 엑셀 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_{today_str}.xlsx")
        else:
            st.warning("⚠️ 포착된 공고가 없습니다.")
    except Exception as e:
        st.error(f"🚨 오류 발생: {e}")
