import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import time
import pytz

# --- [1] 부장님 정예 커스텀 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 🎯 키워드 통합 (18종 확장)
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유물", "음식물", "초본류", "초목류", "폐가구", "대형", "적환장", "반입불가", "매립", "재활용"]
TARGET_AREAS = ["경기도", "평택시", "화성시", "제한없음", "전국", "서울", "인천"]

# 기관 전용 키워드
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 웹 인터페이스 구성 ---
st.set_page_config(page_title="THE RADAR", layout="wide")
st.title("📡 THE RADAR")
st.write("### FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE")
st.divider()

# 사이드바: 수색 범위 설정
st.sidebar.header("🕹️ 수색 범위 설정")
search_days = st.sidebar.slider("조회 범위 (과거/미래 일수)", 1, 20, 10)
kogas_months = st.sidebar.number_input("가스공사 과거 조회 (개월)", 1, 12, 6)

if st.sidebar.button("🔍 전 기관 통합 정밀 수색 개시", type="primary"):
    final_list = []
    stats = {"나라장터": 0, "LH": 0, "국방부": 0, "수자원공사": 0, "가스공사": 0}
    
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    fetch_time = now.strftime("%Y-%m-%d %H:%M:%S")
    st.write(f"⏱️ **레이더 가동 시각:** `{fetch_time}` (KST)")
    
    # 날짜 파라미터 동기화
    start_day = (now - timedelta(days=search_days)).strftime("%Y%m%d")
    today_api = now.strftime("%Y%m%d")
    end_day = (now + timedelta(days=search_days)).strftime("%Y%m%d")
    kogas_start = (now - timedelta(days=kogas_months*30)).strftime("%Y%m%d")
    search_month = now.strftime('%Y%m')

    status_st = st.empty()
    prog = st.progress(0)

    try:
        # --- 1. 나라장터 (G2B) ---
        status_st.info("📡 [1/5] 나라장터 수색 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / 100)
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': start_day+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                for it in ([items] if isinstance(items, dict) else items):
                    if "전자입찰" not in it.get('bidMethdNm', ''): continue
                    final_list.append({'출처': '나라장터', '번호': it.get('bidNtceNo'), '공고명': it.get('bidNtceNm'), '수요기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역': '전국/제한없음', '마감일시': clean_date_strict(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')})
                    stats["나라장터"] += 1
            except: continue

        # --- 2. LH ---
        status_st.info("📡 [2/5] LH 공사 채널 수색 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': start_day, 'tndrbidRegDtEnd': today_api, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, timeout=10)
            res_lh.encoding = res_lh.apparent_encoding
            root = ET.fromstring(f"<root>{re.sub(r'<\?xml.*\\?>', '', res_lh.text).strip()}</root>")
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\\[CDATA\\[|\\]\\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    b_no = item.findtext('bidNum')
                    final_list.append({'출처': 'LH', '번호': b_no, '공고명': bid_nm, '수요기관': 'LH', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), '지역': '전국/상세참조', '마감일시': clean_date_strict(item.findtext('openDtm')), 'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}"})
                    stats["LH"] += 1
        except: pass

        # --- 3. 국방부 (v161.0 정밀 로직 이식) ---
        status_st.info("📡 [3/5] 국방부 전 채널 정밀 분석 중...")
        d2b_configs = [
            {'type': '일반입찰', 'list': 'getDmstcCmpetBidPblancList', 'det': 'getDmstcCmpetBidPblancDetail', 'clos': 'biddocPresentnClosDt'},
            {'type': '공개수의', 'list': 'getDmstcOthbcVltrnNtatPlanList', 'det': 'getDmstcOthbcVltrnNtatPlanDetail', 'clos': 'prqudoPresentnClosDt'}
        ]
        for cfg in d2b_configs:
            try:
                params_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
                if cfg['type'] == '공개수의': params_d.update({'prqudoPresentnClosDateBegin': start_day, 'prqudoPresentnClosDateEnd': end_day})
                
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['list']}", params=params_d, timeout=10).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for it in ([items_d] if isinstance(items_d, dict) else items_d):
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in KEYWORDS):
                        # 🎯 상세 페이지 재조회 (지역/예산 확보)
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if cfg['type'] == '공개수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        area, budget = "제한없음", it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                        try:
                            det_res = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['det']}", params=p_det, timeout=3).json()
                            det_data = det_res.get('response', {}).get('body', {}).get('item', {})
                            area, budget = det_data.get('areaLmttList') or area, det_data.get('budgetAmount') or budget
                        except: pass
                        if any(t in area for t in TARGET_AREAS):
                            final_list.append({'출처': f"국방부({cfg['type']})", '번호': it.get('pblancNo') or it.get('dcsNo'), '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': area, '마감일시': clean_date_strict(it.get(cfg['clos'])), 'URL': 'https://www.d2b.go.kr'})
                            stats["국방부"] += 1
            except: continue

        # --- 4. 수자원공사 ---
        status_st.info("📡 [4/5] K-water 정밀 필터링 중...")
        for kw in KWATER_KEYWORDS:
            try:
                res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", params={'serviceKey': SERVICE_KEY, 'searchDt': search_month, 'bidNm': kw, '_type': 'json'}, timeout=10).json()
                items_k = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for kit in ([items_k] if isinstance(items_k, dict) else items_k):
                    if any(k in kit.get('tndrPblancNm', '') for k in KWATER_KEYWORDS):
                        final_list.append({'출처': '수자원공사', '번호': kit.get('tndrPbanno'), '공고명': kit.get('tndrPblancNm'), '수요기관': '수자원공사', '예산': 0, '지역': '전국/공고참조', '마감일시': clean_date_strict(kit.get('tndrPblancEnddt')), 'URL': f"https://ebid.kwater.or.kr/wq/index.do?tndrPbanno={kit.get('tndrPbanno')}"})
                        stats["수자원공사"] += 1
            except: continue

        # --- 5. 가스공사 ---
        status_st.info("📡 [5/5] 가스공사 6개월 조회 중...")
        try:
            res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': kogas_start}, timeout=10)
            root_kg = ET.fromstring(res_kg.text)
            for item in root_kg.findall('.//item'):
                title = item.findtext('NOTICE_NAME') or '-'
                if any(kw in title for kw in KOGAS_KEYWORDS):
                    final_list.append({'출처': '가스공사', '번호': item.findtext('NOTICE_CODE'), '공고명': title, '수요기관': '가스공사', '예산': 0, '지역': '전국/상세참조', '마감일시': clean_date_strict(item.findtext('END_DT')), 'URL': "https://bid.kogas.or.kr:9443/supplier/index.jsp"})
                    stats["가스공사"] += 1
        except: pass

        # --- 최종 출력 ---
        status_st.empty()
        cols = st.columns(5)
        for i, (name, count) in enumerate(stats.items()):
            cols[i].metric(name, f"{count}건")

        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일시'])
            st.success(f"✅ 총 {len(df)}건의 유효 공고를 포착했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='RADAR')
            st.download_button(label="📥 통합 리포트(Excel) 다운로드", data=output.getvalue(), file_name=f"RADAR_TOTAL_{today_api}.xlsx")
        else:
            st.warning("⚠️ 포착된 공고가 없습니다. 서버 점검 여부를 확인하세요.")
            
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
