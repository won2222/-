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

# --- [1] 부장님 정예 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 기관별 핵심 키워드
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
OUR_LICENSES = ['1226', '1227', '6786', '6770']
# 🎯 부장님 오더: 서울/인천 제외 모드 (경기, 평택, 화성, 전국 집중)
MUST_PASS_AREAS = ['경기', '경기도', '평택', '평택시', '화성', '화성시', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v2500", layout="wide")
st.title("📡 THE RADAR v2500.0")
st.info("🎯 기관별 날짜 규격 최적화 완료: G2B(12자리) / LH·D2B(8자리)")
st.divider()

if st.sidebar.button("🚀 전 채널 규격 맞춤 수색 개시", type="primary"):
    final_list = []
    
    # --- 🎯 [날짜 변환 엔진] 기관별 맞춤 포맷 생성 ---
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 1. 나라장터 전용 (12자리: YYYYMMDDHHMM)
    g2b_start = (now - timedelta(days=7)).strftime("%Y%m%d") + "0000"
    g2b_end   = now.strftime("%Y%m%d") + "2359"
    
    # 2. LH & 국방부 전용 (8자리: YYYYMMDD)
    std_start = (now - timedelta(days=7)).strftime("%Y%m%d")
    std_end   = now.strftime("%Y%m%d")
    
    # 3. 국방부 수의계약 미래 마감용 (8자리)
    d2b_future = (now + timedelta(days=10)).strftime("%Y%m%d")
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- PHASE 1. 나라장터 (12자리 규격 침투) ---
        status_st.info("📡 [1/3] 나라장터 수색 중... (12자리 날짜 적용)")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / (len(KEYWORDS) * 2))
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 
                     'inqryBgnDt': g2b_start, 'inqryEndDt': g2b_end, 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=10).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                for it in ([items] if isinstance(items, dict) else items):
                    b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                    # 면허/지역 2차 검증
                    l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                    lic_str = str(l_res.get('response', {}).get('body', {}).get('items', []))
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                    reg_str = str(r_res.get('response', {}).get('body', {}).get('items', []))
                    
                    if (any(c in lic_str for c in OUR_LICENSES) or "[]" in lic_str) and any(ok in reg_str for ok in MUST_PASS_AREAS):
                        final_list.append({'출처': 'G2B', '번호': b_no, '공고명': it['bidNtceNm'], '수요기관': it['dminsttNm'], '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역': reg_str[:40], '마감일': format_date_clean(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')})
            except: continue

        # --- PHASE 2. LH (8자리 규격 침투) ---
        status_st.info("📡 [2/3] LH 시설공사 수색 중... (8자리 날짜 적용)")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': std_start, 'tndrbidRegDtEnd': std_end, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=20)
            res_lh.encoding = res_lh.apparent_encoding
            root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text).strip())
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    final_list.append({'출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm, '수요기관': 'LH공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), '지역': '전국', '마감일': format_date_clean(item.findtext('openDtm')), 'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"})
        except: pass

        # --- PHASE 3. 국방부 (v161 엔진 & 8자리 규격) ---
        status_st.info("📡 [3/3] 국방부 정밀 수색 중... (SCU번호 확보)")
        d2b_cfg = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail'}, 
                   {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail'}]
        for cfg in d2b_cfg:
            try:
                p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
                if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': std_start, 'prqudoPresentnClosDateEnd': d2b_future})
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, timeout=20).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for it in ([items_d] if isinstance(items_d, dict) else items_d):
                    if any(kw in (it.get('bidNm') or it.get('othbcNtatNm', '')) for kw in KEYWORDS):
                        # 상세 API로 SCU 번호와 지역 필터링
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        try:
                            det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=10).json().get('response', {}).get('body', {}).get('item', {})
                            area = det.get('areaLmttList') or "상세확인"
                            if any(t in area for t in MUST_PASS_AREAS):
                                final_list.append({'출처': f'D2B({cfg["t"]})', '번호': det.get('g2bPblancNo') or it.get('pblancNo'), '공고명': it.get('bidNm') or it.get('othbcNtatNm', ''), '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(det.get('budgetAmount') or it.get('asignBdgtAmt') or 0)), '지역': area, '마감일': format_date_clean(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'})
                        except: pass
            except: continue

        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 수색 완료! 기관별 규격 맞춤으로 {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 v2500 리포트 저장", data=output.getvalue(), file_name=f"RADAR_ALL_FIXED_{std_end}.xlsx")
        else:
            st.warning("⚠️ 현재 조건에 맞는 공고가 없습니다.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
