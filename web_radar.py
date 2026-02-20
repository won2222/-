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

# --- [1] 부장님 v169.0 정예 필터 설정 (원형 보존) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
            "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]

# 🎯 면허 및 지역 필터 (v169.0 원본 규격)
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS = ['경기도', '평택시', '화성시', '서울특별시', '서울', '인천', '전국', '경기']
EXCLUDE_LIST = ['충청', '전라', '강원', '경상', '제주', '부산', '대구', '광주', '대전', '울산', '세종', '충북', '충남', '경북', '경남', '전북', '전남']

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v2800", layout="wide")
st.title("📡 THE RADAR v2800.0")
st.info("🎯 필터 원형 보존 모드: 기관별 날짜 규격(12자리/8자리)만 정밀 수정 완료")

if st.sidebar.button("🚀 정밀 맞춤 수색 개시", type="primary"):
    final_list = []
    status_st = st.empty()
    prog = st.progress(0)
    
    # --- 🎯 [날짜 규격 변환 엔진] 기관별 입맛에 맞게 생성 ---
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 1. G2B용 (12자리: YYYYMMDDHHMM)
    g2b_start = (now - timedelta(days=7)).strftime("%Y%m%d") + "0000"
    g2b_end   = now.strftime("%Y%m%d") + "2359"
    
    # 2. LH/D2B용 (8자리: YYYYMMDD)
    std_start = (now - timedelta(days=7)).strftime("%Y%m%d")
    std_end   = now.strftime("%Y%m%d")
    d2b_future = (now + timedelta(days=7)).strftime("%Y%m%d")

    try:
        # --- PHASE 1. 나라장터 (12자리 & 면허/지역 필터) ---
        status_st.info("📡 [1/3] 나라장터 수색 중... (12자리 규격 적용)")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / (len(KEYWORDS) * 2))
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 
                     'inqryBgnDt': g2b_start, 'inqryEndDt': g2b_end, 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=10).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                for it in ([items] if isinstance(items, dict) else items):
                    b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '00')).zfill(2)
                    
                    # 🎯 부장님 원형 필터 검증 (면허 & 지역)
                    l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                    lic_str = str(l_res.get('response', {}).get('body', {}).get('items', []))
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                    reg_val = str([ri.get('prtcptPsblRgnNm', '') for ri in r_res.get('response', {}).get('body', {}).get('items', [])])

                    lic_ok = any(code in lic_str for code in OUR_LICENSES) or "[]" in lic_str
                    reg_ok = any(ok in reg_val for ok in MUST_PASS)
                    
                    if lic_ok and reg_ok:
                        final_list.append({'출처': '1.나라장터', '번호': b_no, '공고명': it['bidNtceNm'], '수요기관': it['dminsttNm'], '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역': reg_val[:40], '마감일': clean_date_strict(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')})
            except: continue

        # --- PHASE 2. LH (8자리 & 키워드 필터) ---
        status_st.info("📡 [2/3] LH 수색 중... (8자리 규격 적용)")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': std_start, 'tndrbidRegDtEnd': std_end, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=15)
            res_lh.encoding = res_lh.apparent_encoding
            root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text).strip())
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    final_list.append({'출처': '2.LH', '번호': item.findtext('bidNum'), '공고명': bid_nm, '수요기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), '지역': '전국/공고참조', '마감일': clean_date_strict(item.findtext('openDtm')), 'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"})
        except: pass

        # --- PHASE 3. 국방부 (8자리 & SCU 번호 추출) ---
        status_st.info("📡 [3/3] 국방부 수색 중... (8자리 규격 & SCU번호)")
        d2b_cfg = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail'}, 
                   {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail'}]
        for cfg in d2b_cfg:
            try:
                p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
                if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': std_start, 'prqudoPresentnClosDateEnd': d2b_future})
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for it in ([items_d] if isinstance(items_d, dict) else items_d):
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in KEYWORDS):
                        # 상세 API 접속 (예산/참조번호)
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        try:
                            det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=10).json().get('response', {}).get('body', {}).get('item', {})
                            area = det.get('areaLmttList') or "상세확인"
                            if any(t in area for t in MUST_PASS):
                                final_list.append({'출처': f'D2B({cfg["t"]})', '번호': det.get('g2bPblancNo') or it.get('pblancNo'), '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(det.get('budgetAmount') or it.get('asignBdgtAmt') or 0)), '지역': area, '마감일': clean_date_strict(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'})
                        except: pass
            except: continue

        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 작전 완료! {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 v2800 전략 리포트 저장", data=output.getvalue(), file_name=f"RADAR_FINAL_{std_end}.xlsx")
        else:
            st.warning("⚠️ 포착된 공고가 없습니다. 날짜나 키워드를 확인해 보세요.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
