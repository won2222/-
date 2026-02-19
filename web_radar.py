import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz
import time

# --- [1] 핵심 세척 및 포맷 함수 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def lh_korean_cleaner(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>', '', text)
    return text.strip()

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v600", layout="wide")
st.title("📡 THE RADAR v600.0")
st.caption("FRENERGY STRATEGIC PROCUREMENT - FULL INTEGRATED ENGINE")
st.divider()

# --- [3] 사이드바 컨트롤러 (부장님 커스텀 베이스) ---
st.sidebar.header("🛠️ 전략 수색 설정")

# 날짜 설정 (LH 및 전 기관 연동)
st.sidebar.subheader("📅 수색 기간 설정")
col_s, col_e = st.sidebar.columns(2)
with col_s:
    s_date = st.sidebar.date_input("수색 시작일", datetime.now() - timedelta(days=7))
with col_e:
    e_date = st.sidebar.date_input("수색 종료일", datetime.now() + timedelta(days=7))

# 키워드 설정 (부장님 18종 베이스)
st.sidebar.subheader("🔑 핵심 필터 키워드")
default_kw = "폐기물, 운반, 폐목재, 폐합성수지, 식물성, 낙엽, 임목, 가연성, 부유, 잔재물, 반입불가, 초본류, 초목류, 폐가구, 대형, 적환장, 매립, 재활용"
user_kw = st.sidebar.text_area("쉼표(,) 구분 입력", default_kw, height=150)
kw_list = [k.strip() for k in user_kw.split(",") if k.strip()]

# 지역 필터 (경기 최적화)
MUST_PASS_AREAS = ['경기', '평택', '화성', '서울', '인천', '전국', '제한없음']

if st.sidebar.button("🚀 전 구역 통합 정밀 수색 개시", type="primary"):
    final_list = []
    s_str = s_date.strftime("%Y%m%d")
    e_str = e_date.strftime("%Y%m%d")
    today_str = datetime.now().strftime("%Y%m%d")
    search_month = datetime.now().strftime('%Y%m')
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- PHASE 1. LH (정밀 청소 엔진) ---
        status_st.info(f"📡 LH 공사 수색 중... ({s_str} ~ {e_str})")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_str, 'tndrbidRegDtEnd': e_str, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=25)
            res_lh.encoding = res_lh.apparent_encoding
            clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
            if "<resultCode>00</resultCode>" in clean_xml:
                root = ET.fromstring(f"<root>{clean_xml}</root>")
                for item in root.findall('.//item'):
                    bid_nm = lh_korean_cleaner(item.findtext('bidnmKor'))
                    if any(kw in bid_nm for kw in kw_list):
                        final_list.append({
                            '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm,
                            '수요기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce')),
                            '지역': '전국', '마감일': format_date_clean(item.findtext('openDtm')),
                            'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                        })
        except: pass
        prog.progress(20)

        # --- PHASE 2. 국방부 (D2B 정밀 로직) ---
        status_st.info("📡 국방부 마감 타겟 수색 중...")
        d2b_cfg = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail', 'c': 'biddocPresentnClosDt'}, 
                   {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail', 'c': 'prqudoPresentnClosDt'}]
        for cfg in d2b_cfg:
            try:
                p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
                if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': s_str, 'prqudoPresentnClosDateEnd': e_str})
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for it in ([items_d] if isinstance(items_d, dict) else items_d):
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = str(it.get(cfg['c'], ''))[:8]
                    if any(kw in bid_nm for kw in kw_list) and (s_str <= clos_dt <= e_str):
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        area, budget = "상세확인", it.get('asignBdgtAmt') or 0
                        try:
                            det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                            if det: area, budget = det.get('areaLmttList') or area, det.get('budgetAmount') or budget
                        except: pass
                        if any(t in area for t in MUST_PASS_AREAS):
                            final_list.append({'출처': f"D2B({cfg['t']})", '번호': it.get('pblancNo') or it.get('dcsNo'), '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': area, '마감일': format_date_clean(it.get(cfg['c'])), 'URL': 'https://www.d2b.go.kr'})
            except: continue
        prog.progress(40)

        # --- PHASE 3. 나라장터 (G2B) ---
        status_st.info("📡 나라장터 정밀 필터 수색 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in kw_list[:10]:
            try:
                p_g = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_str+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res_g = requests.get(url_g2b, params=p_g).json()
                items_g = res_g.get('response', {}).get('body', {}).get('items', [])
                for it in ([items_g] if isinstance(items_g, dict) else items_g):
                    final_list.append({'출처': 'G2B', '번호': it.get('bidNtceNo'), '공고명': it.get('bidNtceNm'), '수요기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or 0, errors='coerce')), '지역': '전국', '마감일': format_date_clean(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')})
            except: continue
        prog.progress(70)

        # --- PHASE 4. 수자원 & 5. 가스공사 ---
        status_st.info("📡 수자원/가스공사 스캔 중...")
        # 수자원
        try:
            res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", params={'serviceKey': SERVICE_KEY, 'searchDt': search_month, '_type': 'json'}, timeout=10).json()
            k_items = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for kit in ([k_items] if isinstance(k_items, dict) else k_items):
                if any(kw in kit.get('tndrPblancNm', '') for kw in kw_list):
                    final_list.append({'출처': 'K-water', '번호': kit.get('tndrPbanno'), '공고명': kit.get('tndrPblancNm'), '수요기관': '수자원공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(kit.get('tndrPblancEnddt')), 'URL': 'https://ebid.kwater.or.kr'})
        except: pass
        # 가스공사
        try:
            res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': s_str}, timeout=15)
            root_kg = ET.fromstring(res_kg.text)
            for item in root_kg.findall('.//item'):
                title = item.findtext('NOTICE_NAME') or '-'
                if any(kw in title for kw in kw_list):
                    final_list.append({'출처': 'KOGAS', '번호': item.findtext('NOTICE_CODE') or '-', '공고명': title, '수요기관': '가스공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(item.findtext('END_DT')), 'URL': 'https://k-ebid.kogas.or.kr'})
        except: pass
        prog.progress(100)

        # --- [결과 출력] ---
        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 작전 완료! LH 포함 총 {len(df)}건 확보.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='RADAR')
            st.download_button(label="📥 통합 리포트(Excel) 저장", data=output.getvalue(), file_name=f"RADAR_v600_{s_str}.xlsx")
        else:
            st.warning("⚠️ 포착된 공고가 없습니다. 기간이나 키워드를 조정해 보세요.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
