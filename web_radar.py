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

# --- [1] 기본 유틸리티 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def lh_cleaner(text):
    if not text: return ""
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

def date_fmt(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v650", layout="wide")
st.title("📡 THE RADAR v650.0")
st.subheader("기관별 독립 수색 엔진 가동")

# --- [3] 사이드바: 수색 설정 ---
st.sidebar.header("🕹️ 수색 엔진 설정")
col_s, col_e = st.sidebar.columns(2)
with col_s:
    s_date = st.sidebar.date_input("수색 시작일", datetime.now() - timedelta(days=7))
with col_e:
    e_date = st.sidebar.date_input("수색 종료일", datetime.now() + timedelta(days=7))

st.sidebar.subheader("🔑 필터 키워드")
default_kw = "폐기물, 운반, 폐목재, 임목, 나무, 벌채, 뿌리, 재활용, 가연성, 잔재물"
user_kw = st.sidebar.text_area("쉼표 구분", default_kw, height=100)
kw_list = [k.strip() for k in user_kw.split(",") if k.strip()]

# 면허 및 지역 필터 (나라장터용)
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기', '평택', '화성', '서울', '인천', '전국', '제한없음']

if st.sidebar.button("🚀 전 구역 정밀 수색 시작", type="primary"):
    final_list = []
    s_str = s_date.strftime("%Y%m%d")
    e_str = e_date.strftime("%Y%m%d")
    today_str = datetime.now().strftime("%Y%m%d")
    
    prog = st.progress(0)
    status = st.empty()

    # --- 1. 나라장터 (정밀 필터링 모드) ---
    status.info("📡 [나라장터] 면허/지역 필터 수색 중...")
    url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
    for i, kw in enumerate(kw_list):
        try:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_str+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                if "전자입찰" not in it.get('bidMethdNm', ''): continue
                b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                # 🎯 면허/지역 2차 필터링
                try:
                    l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                    lic_val = str(l_res.get('response', {}).get('body', {}).get('items', []))
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                    reg_val = str(r_res.get('response', {}).get('body', {}).get('items', []))
                    
                    if (any(lc in lic_val for lc in OUR_LICENSES) or "[]" in lic_val) and any(ar in reg_val for ar in MUST_PASS_AREAS):
                        final_list.append({'출처':'G2B', '번호':b_no, '공고명':it['bidNtceNm'], '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역':reg_val, '마감일':date_fmt(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
                except: continue
        except: continue
    prog.progress(30)

    # --- 2. LH (성공했던 청소 로직 복구) ---
    status.info("📡 [LH공사] XML 청소 및 정밀 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_str, 'tndrbidRegDtEnd': e_str, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=20)
        res_lh.encoding = res_lh.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        for item in root.findall('.//item'):
            bid_nm = lh_cleaner(item.findtext('bidnmKor'))
            if any(kw in bid_nm for kw in kw_list):
                final_list.append({'출처':'LH', '번호':item.findtext('bidNum'), '공고명':bid_nm, '수요기관':'LH공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), '지역':'전국', '마감일':date_fmt(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"})
    except: pass
    prog.progress(60)

    # --- 3. 국방부 (v161.0 정밀 파싱 복구) ---
    status.info("📡 [국방부] 상세 페이지 추적 및 예산 분석 중...")
    d2b_configs = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail', 'c': 'biddocPresentnClosDt'}, 
                  {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail', 'c': 'prqudoPresentnClosDt'}]
    for cfg in d2b_configs:
        try:
            p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
            if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': s_str, 'prqudoPresentnClosDateEnd': e_str})
            res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d).json()
            items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for it in ([items_d] if isinstance(items_d, dict) else items_d):
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                clos_dt = str(it.get(cfg['c'], ''))[:8]
                if any(kw in bid_nm for kw in kw_list) and (s_str <= clos_dt <= e_str):
                    # 🎯 국방부 핵심: 상세 페이지 재조회로 예산/지역 확정
                    p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                    if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                    try:
                        det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                        if any(ar in str(det.get('areaLmttList','')) for ar in MUST_PASS_AREAS):
                            final_list.append({'출처': f"D2B({cfg['t']})", '번호': it.get('pblancNo'), '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(det.get('budgetAmount') or it.get('asignBdgtAmt') or 0)), '지역': det.get('areaLmttList'), '마감일': date_fmt(it.get(cfg['c'])), 'URL': 'https://www.d2b.go.kr'})
                    except: continue
        except: continue
    prog.progress(100)

    # --- [결과 출력] ---
    status.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
        st.success(f"✅ 수색 완료! 총 {len(df)}건의 정예 공고 확보.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 통합 리포트 저장", data=output.getvalue(), file_name=f"RADAR_v650_{s_str}.xlsx")
    else:
        st.warning("⚠️ 포착된 공고가 없습니다. 날짜나 키워드를 확인해 보세요.")
