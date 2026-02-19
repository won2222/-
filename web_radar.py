import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re

# --- [1] 기본 설정 및 세척 함수 ---
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

# --- [2] UI 레이아웃 ---
st.set_page_config(page_title="THE RADAR v700", layout="wide")
st.title("📡 THE RADAR v700.0")
st.caption("부장님 전용 베이스 로직(나라장터/국방부/LH) 통합판")

# --- [3] 사이드바 설정 ---
st.sidebar.header("🕹️ 수색 엔진 설정")
s_date = st.sidebar.date_input("수색 시작일", datetime.now() - timedelta(days=14))
e_date = st.sidebar.date_input("수색 종료일", datetime.now() + timedelta(days=7))

user_kw = st.sidebar.text_area("필터 키워드", "폐기물, 운반, 폐목재, 임목, 나무, 벌채, 뿌리, 재활용, 잔재물, 가연성", height=100)
kw_list = [k.strip() for k in user_kw.split(",") if k.strip()]

# 부장님 베이스 필터 조건
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기', '평택', '화성', '서울', '인천', '전국', '제한없음']

if st.sidebar.button("🚀 베이스 로직으로 전체 수색", type="primary"):
    final_list = []
    s_str = s_date.strftime("%Y%m%d")
    e_str = e_date.strftime("%Y%m%d")
    today_str = datetime.now().strftime("%Y%m%d")
    
    status = st.empty()
    prog = st.progress(0)

    # --- 🎯 1. LH (검증된 정밀 로직) ---
    status.info("📡 [LH] 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_str, 'tndrbidRegDtEnd': e_str, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=20)
        res_lh.encoding = res_lh.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        for item in root.findall('.//item'):
            bid_nm = lh_cleaner(item.findtext('bidnmKor', ''))
            if any(kw in bid_nm for kw in kw_list):
                final_list.append({
                    '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm,
                    '수요기관': 'LH공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                    '지역': '전국', '마감일': date_fmt(item.findtext('openDtm')),
                    'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                })
    except: pass
    prog.progress(33)

    # --- 🎯 2. 나라장터 (베이스 필터 로직 복원) ---
    status.info("📡 [나라장터] 면허/지역 정밀 대조 중...")
    url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
    for kw in kw_list:
        try:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_str+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=10).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                
                # 면허 필터 (구조 분해)
                l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                l_items = l_res.get('response', {}).get('body', {}).get('items', [])
                lic_names = [li.get('lcnsLmtNm', '') for li in (l_items if isinstance(l_items, list) else [l_items])]
                
                # 지역 필터 (부장님이 주신 딕셔너리 구조 대응)
                r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                r_items = r_res.get('response', {}).get('body', {}).get('items', [])
                reg_names = [ri.get('prtcptPsblRgnNm', '') for ri in (r_items if isinstance(r_items, list) else [r_items])]
                
                # 베이스 필터링 조건
                lic_ok = not lic_names or any(any(code in name for code in OUR_LICENSES) for name in lic_names)
                reg_ok = not reg_names or any(any(area in name for area in MUST_PASS_AREAS) for name in reg_names)

                if lic_ok and reg_ok:
                    final_list.append({
                        '출처': 'G2B', '번호': b_no, '공고명': it.get('bidNtceNm'), '수요기관': it.get('dminsttNm'),
                        '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역': ", ".join(reg_names) or "전국",
                        '마감일': date_fmt(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')
                    })
        except: continue
    prog.progress(66)

    # --- 🎯 3. 국방부 (상세 파싱 베이스 복원) ---
    status.info("📡 [국방부] 상세 정보 추적 중...")
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
                if any(kw in bid_nm for kw in kw_list):
                    # 상세 정보를 가져와서 예산과 지역 최종 확인
                    p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                    if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                    try:
                        det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                        if det and any(area in str(det.get('areaLmttList','')) for area in MUST_PASS_AREAS):
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
        st.success(f"✅ 베이스 로직 수색 완료! 총 {len(df)}건 확보.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
    else:
        st.warning("⚠️ 포착된 공고가 없습니다. 날짜나 키워드를 확인해 보세요.")
