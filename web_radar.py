import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re

# --- [1] 부장님 베이스 유틸리티 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def lh_cleaner(text):
    if not text: return ""
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip()

def date_fmt(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v980", layout="wide")
st.title("📡 THE RADAR v980.0")
st.caption("FRENERGY STRATEGIC PROCUREMENT - BASE LOGIC FULL RESTORED")

# --- [3] 사이드바 설정 ---
st.sidebar.header("🕹️ LH 수색 기간 (직접 지정)")
lh_s_date = st.sidebar.date_input("LH 시작일", datetime.now() - timedelta(days=14))
lh_e_date = st.sidebar.date_input("LH 종료일", datetime.now() + timedelta(days=7))

# 🎯 키워드 셋팅
G2B_KW = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
CORE_KW = ["폐목재", "폐가구", "임목", "폐기물", "낙엽"]

# 🎯 지역 및 면허 필터 (강제 제외 리스트 삭제)
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기', '평택', '화성', '전국', '제한없음', '서울', '인천'] 

if st.sidebar.button("🚀 베이스 로직 통합 수색 개시", type="primary"):
    final_list = []
    now = datetime.now()
    lh_s, lh_e = lh_s_date.strftime("%Y%m%d"), lh_e_date.strftime("%Y%m%d")
    
    # 나라장터/국방부 자동 날짜 설정
    g2b_s = (now - timedelta(days=7)).strftime("%Y%m%d")
    g2b_e = now.strftime("%Y%m%d")
    d2b_future = (now + timedelta(days=7)).strftime("%Y%m%d")

    status = st.empty()
    prog = st.progress(0)

    # --- PHASE 1. LH (부장님 성공 로직) ---
    status.info("📡 [LH] 정밀 청소 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': lh_s, 'tndrbidRegDtEnd': lh_e, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=20)
        res_lh.encoding = res_lh.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        for item in root.findall('.//item'):
            bid_nm = lh_cleaner(item.findtext('bidnmKor', ''))
            if any(kw in bid_nm for kw in CORE_KW):
                final_list.append({
                    '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm,
                    '수요기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                    '지역': '전국', '마감일': date_fmt(item.findtext('openDtm')),
                    'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                })
    except: pass
    prog.progress(33)

    # --- PHASE 2. 나라장터 (베이스 필터 로직) ---
    status.info("📡 [나라장터] 면허/지역 정밀 대조 중...")
    url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
    for kw in G2B_KW:
        try:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': g2b_s+'0000', 'inqryEndDt': g2b_e+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                
                # 지역 정보 상세 확인
                r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                regs = r_res.get('response', {}).get('body', {}).get('items', [])
                reg_names = [rd.get('prtcptPsblRgnNm', '') for rd in (regs if isinstance(regs, list) else [regs])]
                
                # 강제 제외 없이 타겟 지역 포함 여부만 확인
                is_pass = not reg_names or any(ar in str(reg_names) for ar in MUST_PASS_AREAS)

                if is_pass:
                    final_list.append({
                        '출처': 'G2B', '번호': b_no, '공고명': it.get('bidNtceNm'), '수요기관': it.get('dminsttNm'),
                        '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역': ", ".join(reg_names) or "전국",
                        '마감일': date_fmt(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')
                    })
        except: continue
    prog.progress(66)

    # --- PHASE 3. 국방부 (상세 페이지 예산 파싱) ---
    status.info("📡 [국방부] 상세 정보 추적 중...")
    d2b_cfg = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail', 'c': 'biddocPresentnClosDt'}, 
               {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail', 'c': 'prqudoPresentnClosDt'}]
    for cfg in d2b_cfg:
        try:
            p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}
            if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': g2b_e, 'prqudoPresentnClosDateEnd': d2b_future})
            res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d).json()
            items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for it in ([items_d] if isinstance(items_d, dict) else items_d):
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                if any(kw in bid_nm for kw in CORE_KW):
                    p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                    if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                    try:
                        det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                        # 지역 필터링 (경기/서울/인천 등 타겟 지역 포함 확인)
                        area_list = str(det.get('areaLmttList', ''))
                        if not area_list or any(ar in area_list for ar in MUST_PASS_AREAS):
                            final_list.append({
                                '출처': f"D2B({cfg['t']})", '번호': it.get('pblancNo') or it.get('dcsNo'), '공고명': bid_nm,
                                '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(det.get('budgetAmount') or it.get('asignBdgtAmt') or 0)),
                                '지역': det.get('areaLmttList') or "상세참조", '마감일': date_fmt(it.get(cfg['c'])), 'URL': 'https://www.d2b.go.kr'
                            })
                    except: continue
        except: continue
    prog.progress(100)

    # --- [최종 결과] ---
    status.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
        st.success(f"✅ 베이스 로직 통합 수색 완료! 총 {len(df)}건 확보.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_BASE_V980.xlsx")
    else:
        st.warning("⚠️ 포착된 공고가 없습니다.")
