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

# --- [1] 부장님 정예 커스텀 설정 (v169/v90 통합) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 기관별 맞춤 키워드
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
LH_KEYWORDS_REGEX = '폐목재|임목|목재|나무|벌채|뿌리|폐기물|운반|재활용' # v90 전용
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '전국', '제한없음']

# 베이스 URL
KWATER_DETAIL_BASE = "https://ebid.kwater.or.kr/wq/index.do?w2xPath=/ui/index.xml&view=/bidpblanc/bidpblancsttus/BIDBD32000002.xml&tndrPbanno="
KOGAS_HOME = "https://k-ebid.kogas.or.kr"

# --- [2] 보조 엔진 (클리너 및 날짜 정규화) ---
def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

def lh_korean_cleaner(text):
    if not text: return ""
    # v90 핵심: CDATA 장벽 파쇄
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

# --- [3] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v6000", layout="wide")
st.title("📡 THE RADAR v6000.0")
st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE - ALL-IN-ONE RADAR")
st.divider()

KST = pytz.timezone('Asia/Seoul')
now = datetime.now(KST)
s_date_display = (now - timedelta(days=7)).strftime("%Y-%m-%d")
st.sidebar.success(f"📅 **7일 집중 수색 범위**\n\n{s_date_display} ~ 오늘")

if st.sidebar.button("🔍 전 채널 통합 수색 개시", type="primary"):
    final_list = []
    
    # 날짜 파라미터 (7일 고정)
    s_date = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m')
    target_end_day = (now + timedelta(days=7)).strftime("%Y%m%d")
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 (G2B) ---
        status_st.info("📡 [1/5] 나라장터 수색 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=10).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    if "전자입찰" not in it.get('bidMethdNm', ''): continue
                    b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                    
                    # 지역 검증 (부장님 MUST_PASS 로직)
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                    reg_items = r_res.get('response', {}).get('body', {}).get('items', [])
                    reg_val = ", ".join(list(set([ri.get('prtcptPsblRgnNm','') for ri in (reg_items if isinstance(reg_items, list) else [reg_items]) if ri.get('prtcptPsblRgnNm')]))) or "전국"
                    
                    if any(ok in reg_val for ok in MUST_PASS_AREAS):
                        final_list.append({'출처':'G2B', '번호':b_no, '공고명':it['bidNtceNm'], '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역':reg_val, '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
            except: continue
        prog.progress(20)

        # --- 2. LH (e-Bid) - v90.0 시설공사 정밀 타격 ---
        status_st.info("📡 [2/5] LH 시설공사(Gb:1) CDATA 파쇄 수색 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            # v90 핵심: cstrtnJobGb: '1'
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=15)
            res_lh.encoding = res_lh.apparent_encoding
            clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                bid_nm = lh_korean_cleaner(item.findtext('bidnmKor', ''))
                # v90 핵심: 정규표현식 매칭
                if re.search(LH_KEYWORDS_REGEX, bid_nm, re.IGNORECASE):
                    b_no = item.findtext('bidNum')
                    final_list.append({'출처':'LH(시설)', '번호':b_no, '공고명':bid_nm, '수요기관':'한국토지주택공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), '지역':'전국/공고참조', '마감일':format_date_clean(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"})
        except: pass
        prog.progress(40)

        # --- 3. 국방부 (D2B) - v169.0 정밀 예산/수의 로직 ---
        status_st.info("📡 [3/5] 국방부 일반/수의 정밀 수색 중...")
        d2b_configs = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail', 'c': 'biddocPresentnClosDt'}, {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail', 'c': 'prqudoPresentnClosDt'}]
        for cfg in d2b_configs:
            try:
                p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
                if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': s_date, 'prqudoPresentnClosDateEnd': target_end_day})
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, headers=HEADERS, timeout=15).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in KEYWORDS):
                        # v169 핵심: 예산 3중 파싱 및 g2bPblancNo 확보
                        p_no, d_year, d_no = str(it.get('pblancNo', '')), str(it.get('demandYear', '')), str(it.get('dcsNo', ''))
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': p_no, 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': d_year, 'orntCode': it.get('orntCode'), 'dcsNo': d_no, '_type': 'json'}
                        if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                        try:
                            det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                            if det: budget, p_no = det.get('budgetAmount') or budget, det.get('g2bPblancNo') or p_no
                        except: pass
                        final_list.append({'출처': f"D2B({cfg['t']})", '번호': p_no, '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': "공고참조", '마감일': format_date_clean(it.get(cfg['c'])), 'URL': 'https://www.d2b.go.kr'})
            except: continue
        prog.progress(60)

        # --- 4. 수자원공사 ---
        status_st.info("📡 [4/5] K-water 수색 중...")
        for kw in KWATER_KEYWORDS:
            try:
                res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", params={'serviceKey': SERVICE_KEY, 'searchDt': search_month, 'bidNm': kw, '_type': 'json'}, timeout=10).json()
                k_items = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                k_items = [k_items] if isinstance(k_items, dict) else k_items
                for kit in k_items:
                    final_list.append({'출처': 'K-water', '번호': kit.get('tndrPbanno'), '공고명': kit.get('tndrPblancNm'), '수요기관': '한국수자원공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(kit.get('tndrPblancEnddt')), 'URL': f"{KWATER_DETAIL_BASE}{kit.get('tndrPbanno')}"})
            except: continue
        prog.progress(80)

        # --- 5. 가스공사 ---
        status_st.info("📡 [5/5] KOGAS 수색 중...")
        try:
            res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': (now - timedelta(days=30)).strftime("%Y%m%d")}, timeout=15)
            root_kg = ET.fromstring(res_kg.text)
            for item in root_kg.findall('.//item'):
                title = item.findtext('NOTICE_NAME') or '-'
                if any(kw in title for kw in KOGAS_KEYWORDS):
                    final_list.append({'출처': 'KOGAS', '번호': item.findtext('NOTICE_CODE') or '-', '공고명': title, '수요기관': '한국가스공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(item.findtext('END_DT')), 'URL': KOGAS_HOME})
        except: pass
        prog.progress(100)

        # --- [최종 결과 처리] ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호'])
            df['마감일'] = df['마감일'].astype(str)
            df = df.sort_values(by=['마감일'])
            
            # 메트릭 표시
            counts = df['출처'].value_counts()
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("G2B", f"{counts.get('G2B', 0)}건")
            m2.metric("LH(시설)", f"{counts.get('LH(시설)', 0)}건")
            m3.metric("D2B", f"{counts.get('D2B(일반)',0)+counts.get('D2B(수의)',0)}건")
            m4.metric("K-water", f"{counts.get('K-water', 0)}건")
            m5.metric("KOGAS", f"{counts.get('KOGAS', 0)}건")

            st.success(f"✅ 수색 완료! 총 {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            # 엑셀 다운로드
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='RADAR_REPORT')
            st.download_button(label="📥 통합 리포트(Excel) 다운로드", data=output.getvalue(), file_name=f"INTEGRATED_RADAR_{today_str}.xlsx")
        else:
            st.warning("⚠️ 최근 7일 내 조건에 맞는 공고가 없습니다.")

    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
