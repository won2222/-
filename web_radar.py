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

# 통합 키워드 및 지역 필터
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']
OUR_LICENSES = ['1226', '1227', '6786', '6770']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 웹 인터페이스 구성 ---
st.set_page_config(page_title="THE RADAR v300", layout="wide")
st.title("📡 THE RADAR: 통합 관제 시스템")
st.write("### 부장님 v161.0 국방부 정밀 로직 및 5대 기관 통합")
st.divider()

if st.sidebar.button("🔍 전 구역 통합 수색 시작", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 날짜 파라미터 (부장님 소스 동기화)
    s_date = (now - timedelta(days=4)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=3)).strftime("%Y%m%d")
    kogas_start = (now - timedelta(days=180)).strftime("%Y%m%d")
    search_month = now.strftime('%Y%m')

    status_st = st.empty()
    prog = st.progress(0)

    try:
        # --- PHASE 1. 나라장터 (G2B) ---
        status_st.info(f"📡 [1단계] 나라장터 수집 중... ({s_date} ~ {today_str})")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / 100)
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                for it in ([items] if isinstance(items, dict) else items):
                    if "전자입찰" not in it.get('bidMethdNm', ''): continue
                    final_list.append({'출처':'나라장터', '번호':it.get('bidNtceNo'), '공고명':it.get('bidNtceNm'), '수요기관':it.get('dminsttNm'), '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역':'전국', '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
            except: continue

        # --- PHASE 2. LH ---
        status_st.info("📡 [2단계] LH 시설공사 수집 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=10)
            root = ET.fromstring(f"<root>{re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()}</root>")
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    final_list.append({'출처':'LH', '번호':item.findtext('bidNum'), '공고명':bid_nm, '수요기관':'한국토지주택공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), '지역':'전국/상세', '마감일':format_date_clean(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"})
        except: pass

        # --- PHASE 3. 국방부 (부장님 v161.0 정밀 로직) ---
        status_st.info(f"📡 [3단계] 국방부 v161.0 정밀 수색 중 ({tomorrow_str} ~ {target_end_day})")
        api_configs = [
            {'type': '일반입찰', 'list': 'getDmstcCmpetBidPblancList', 'det': 'getDmstcCmpetBidPblancDetail', 'clos': 'biddocPresentnClosDt'},
            {'type': '공개수의', 'list': 'getDmstcOthbcVltrnNtatPlanList', 'det': 'getDmstcOthbcVltrnNtatPlanDetail', 'clos': 'prqudoPresentnClosDt'}
        ]
        for cfg in api_configs:
            url_list = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['list']}"
            p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
            if cfg['type'] == '공개수의': p_d.update({'prqudoPresentnClosDateBegin': s_date, 'prqudoPresentnClosDateEnd': target_end_day})
            try:
                res_d = requests.get(url_list, params=p_d, headers=HEADERS, timeout=10).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for it in ([items_d] if isinstance(items_d, dict) else items_d):
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = str(it.get(cfg['clos']))[:8]
                    if any(kw in bid_nm for kw in KEYWORDS) and (cfg['type'] == '공개수의' or (tomorrow_str <= clos_dt <= target_end_day)):
                        # v161.0 정밀 상세 파싱
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if cfg['type'] == '공개수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        
                        area, budget, combined_no = "국방부상세", it.get('asignBdgtAmt') or it.get('budgetAmount') or 0, it.get('pblancNo')
                        try:
                            det_res = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['det']}", params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                            if det_res:
                                area = det_res.get('areaLmttList') or area
                                budget = det_res.get('budgetAmount') or budget
                                combined_no = det_res.get('g2bPblancNo') or combined_no
                        except: pass
                        
                        if any(t in area for t in MUST_PASS_AREAS):
                            final_list.append({'출처':f"국방부({cfg['type']})", '번호':combined_no, '공고명':bid_nm, '수요기관':it.get('ornt'), '예산':int(pd.to_numeric(budget, errors='coerce') or 0), '지역':area, '마감일':format_date_clean(it.get(cfg['clos'])), 'URL':'https://www.d2b.go.kr'})
            except: continue

        # --- PHASE 4. 수자원공사 (v181.0) ---
        status_st.info("📡 [4단계] 수자원공사 정밀 수색 중...")
        for kw in ["부유물", "식물성", "초본류", "폐목재"]:
            try:
                res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", params={'serviceKey': SERVICE_KEY, 'searchDt': search_month, 'bidNm': kw, '_type': 'json'}, timeout=10).json()
                items_k = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for kit in ([items_k] if isinstance(items_k, dict) else items_k):
                    if any(k in kit.get('tndrPblancNm','') for k in ["부유물", "식물성", "초본류", "폐목재"]):
                        final_list.append({'출처':'수자원공사', '번호':kit.get('tndrPbanno'), '공고명':kit.get('tndrPblancNm'), '수요기관':'한국수자원공사', '예산':0, '지역':'공고참조', '마감일':format_date_clean(kit.get('tndrPblancEnddt')), 'URL':f"https://ebid.kwater.or.kr/wq/index.do?tndrPbanno={kit.get('tndrPbanno')}"})
            except: continue

        # --- PHASE 5. 가스공사 (v193.0) ---
        status_st.info("📡 [5단계] 가스공사 6개월치 스캔 중...")
        try:
            res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': kogas_start}, timeout=10)
            root_kg = ET.fromstring(res_kg.text)
            for item in root_kg.findall('.//item'):
                title = item.findtext('NOTICE_NAME') or '-'
                if any(kw in title for kw in ["폐목재", "가연성", "임목"]):
                    final_list.append({'출처':'가스공사', '번호':item.findtext('NOTICE_CODE'), '공고명':title, '수요기관':'한국가스공사', '예산':0, '지역':'전국', '마감일':format_date_clean(item.findtext('END_DT')), 'URL':"https://k-ebid.kogas.or.kr"})
        except: pass

        # --- [최종 결과 처리] ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 작전 성공! 총 {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='RADAR')
            st.download_button(label="📥 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_{today_str}.xlsx")
        else:
            st.warning("⚠️ 현재 조건에 맞는 공고가 레이더에 잡히지 않습니다.")
            
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
