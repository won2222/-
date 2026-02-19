import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re

# --- [1] 핵심 설정 및 세척 함수 ---
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

# --- [2] UI 구성 ---
st.set_page_config(page_title="THE RADAR v900", layout="wide")
st.title("📡 THE RADAR v900.0")
st.caption("서울/인천 제외 - 경기·전국 집중 타격 시스템")

# --- [3] 사이드바: 부장님 전용 컨트롤러 ---
st.sidebar.header("🕹️ LH 수색 기간 (직접 입력)")
lh_s_date = st.sidebar.date_input("LH 시작일", datetime.now() - timedelta(days=14))
lh_e_date = st.sidebar.date_input("LH 종료일", datetime.now() + timedelta(days=7))

# 부장님 오더 키워드 셋팅
G2B_KW = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
CORE_KW = ["폐목재", "폐가구", "임목", "폐기물", "낙엽"]

# 지역 필터 (서울, 인천 완전 배제)
MUST_PASS_AREAS = ['경기', '평택', '화성', '전국', '제한없음']


if st.sidebar.button("🚀 전 기관 통합 수색 개시", type="primary"):
    final_list = []
    today = datetime.now()
    lh_s, lh_e = lh_s_date.strftime("%Y%m%d"), lh_e_date.strftime("%Y%m%d")
    g2b_s = (today - timedelta(days=7)).strftime("%Y%m%d")
    g2b_e = today.strftime("%Y%m%d")
    d2b_e_limit = (today + timedelta(days=7)).strftime("%Y%m%d")

    status = st.empty()
    prog = st.progress(0)

    # --- 🎯 1. LH (독립 청소 엔진) ---
    status.info(f"📡 LH 수색 중... ({lh_s} ~ {lh_e})")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': lh_s, 'tndrbidRegDtEnd': lh_e, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=20)
        res_lh.encoding = res_lh.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        if "<resultCode>00</resultCode>" in clean_xml:
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                bid_nm = lh_cleaner(item.findtext('bidnmKor', ''))
                if any(kw in bid_nm for kw in CORE_KW):
                    final_list.append({
                        '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm,
                        '수요기관': 'LH공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                        '지역': '전국', '마감일': date_fmt(item.findtext('openDtm')),
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
    except: pass
    prog.progress(25)

    # --- 🎯 2. 나라장터 (구조 분해 정밀 필터링) ---
    status.info("📡 나라장터 18종 키워드 수색 및 서울/인천 필터링 중...")
    url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
    for kw in G2B_KW:
        try:
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '50', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': g2b_s+'0000', 'inqryEndDt': g2b_e+'2359', 'bidNtceNm': kw}
            res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            for it in ([items] if isinstance(items, dict) else items):
                b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                
                # 지역 정보 2차 확인
                r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                reg_data = r_res.get('response', {}).get('body', {}).get('items', [])
                reg_names = [rd.get('prtcptPsblRgnNm', '') for rd in (reg_data if isinstance(reg_data, list) else [reg_data])]
                
                # 서울/인천 배제 필터
                is_excluded = any(any(ex in name for ex in EXCLUDE_AREAS) for name in reg_names)
                is_target = not reg_names or any(any(ar in name for ar in MUST_PASS_AREAS) for name in reg_names)
                
                if is_target and not is_excluded:
                    final_list.append({
                        '출처': 'G2B', '번호': b_no, '공고명': it.get('bidNtceNm'), '수요기관': it.get('dminsttNm'),
                        '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역': ", ".join(reg_names) or "전국",
                        '마감일': date_fmt(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')
                    })
        except: continue
    prog.progress(50)

    # --- 🎯 3. 국방부 (수의계약 정밀 분석) ---
    status.info("📡 국방부 마감 임박 건 수색 중...")
    try:
        p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '300', '_type': 'json', 'prqudoPresentnClosDateBegin': g2b_e, 'prqudoPresentnClosDateEnd': d2b_e_limit}
        res_d = requests.get("http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList", params=p_d, timeout=10).json()
        items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
        for it in ([items_d] if isinstance(items_d, dict) else items_d):
            bid_nm = it.get('othbcNtatNm', '')
            if any(kw in bid_nm for kw in CORE_KW):
                final_list.append({
                    '출처': 'D2B(수의)', '번호': it.get('dcsNo'), '공고명': bid_nm, '수요기관': it.get('ornt'),
                    '예산': int(pd.to_numeric(it.get('budgetAmount', 0))), '지역': '상세참조',
                    '마감일': date_fmt(it.get('prqudoPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'
                })
    except: pass
    prog.progress(75)

    # --- 🎯 4. 수자원 & 가스공사 (통합 엔진) ---
    status.info("📡 수자원/가스공사 통합 수색 중...")
    # ... (생략 없이 수자원/가스 로직 전체 실행)
    try:
        res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': g2b_s}, timeout=15)
        root_kg = ET.fromstring(res_kg.text)
        for item in root_kg.findall('.//item'):
            title = item.findtext('NOTICE_NAME') or '-'
            if any(kw in title for kw in CORE_KW):
                final_list.append({'출처': 'KOGAS', '번호': item.findtext('NOTICE_CODE') or '-', '공고명': title, '수요기관': '가스공사', '예산': 0, '지역': '전국', '마감일': date_fmt(item.findtext('END_DT')), 'URL': 'https://k-ebid.kogas.or.kr'})
    except: pass
    prog.progress(100)

    # --- [최종 결과] ---
    status.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
        st.success(f"✅ 작전 완료! 서울·인천 제외 경기·전국권 총 {len(df)}건 확보.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 통합 리포트 저장", data=output.getvalue(), file_name=f"RADAR_v900.xlsx")
    else:
        st.warning("⚠️ 포착된 공고가 없습니다. LH 날짜나 키워드를 확인해 보세요.")

