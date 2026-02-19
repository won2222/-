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

# 정예 키워드 및 필터 조건
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

# 베이스 URL
KWATER_DETAIL_BASE = "https://ebid.kwater.or.kr/wq/index.do?w2xPath=/ui/index.xml&view=/bidpblanc/bidpblancsttus/BIDBD32000002.xml&tndrPbanno="
KOGAS_HOME = "https://k-ebid.kogas.or.kr"

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR", layout="wide")

st.title("📡 THE RADAR")
st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE - CUSTOM LH SEARCH")
st.divider()

# --- [사이드바: LH 날짜 컨트롤러] ---
st.sidebar.header("🕹️ LH 전용 수색 설정")
lh_s_date = st.sidebar.date_input("LH 수색 시작일", datetime.now() - timedelta(days=14))
lh_e_date = st.sidebar.date_input("LH 수색 종료일", datetime.now() + timedelta(days=7))

if st.sidebar.button("🔍 전 기관 정밀 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 🎯 기관별 날짜 파라미터 세팅
    # LH: 부장님이 입력한 날짜 직공
    lh_s_str = lh_s_date.strftime("%Y%m%d")
    lh_e_str = lh_e_date.strftime("%Y%m%d")
    
    # G2B/기타: 기존 로직대로 7일 고정
    s_date_7 = (now - timedelta(days=7)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m') 
    kogas_start = (now - timedelta(days=180)).strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=7)).strftime("%Y%m%d")
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 (G2B) - 기존 로직 유지 ---
        status_st.info("📡 [1/5] 나라장터 수색 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / 100)
            try:
                time.sleep(0.05)
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date_7+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    if "전자입찰" not in it.get('bidMethdNm', ''): continue
                    b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                    try:
                        l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                        lic_items = l_res.get('response', {}).get('body', {}).get('items', [])
                        lic_val = " / ".join(list(set([li.get('lcnsLmtNm','') for li in (lic_items if isinstance(lic_items, list) else [lic_items]) if li.get('lcnsLmtNm')]))) or "공고참조"
                        r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                        reg_items = r_res.get('response', {}).get('body', {}).get('items', [])
                        reg_val = ", ".join(list(set([ri.get('prtcptPsblRgnNm','') for ri in (reg_items if isinstance(reg_items, list) else [reg_items]) if ri.get('prtcptPsblRgnNm')]))) or "전국"
                        if (any(code in lic_val for code in OUR_LICENSES) or "공고참조" in lic_val) and any(ok in reg_val for ok in MUST_PASS_AREAS):
                            final_list.append({'출처':'G2B', '번호':b_no, '공고명':it['bidNtceNm'], '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역':reg_val, '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
                    except: continue
            except: continue

        # --- 2. LH (부장님 요청: 날짜 지정 연동) ---
        status_st.info(f"📡 [2/5] LH 수색 중... ({lh_s_str} ~ {lh_e_str})")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            # 🎯 부장님이 사이드바에서 고른 날짜(lh_s_str, lh_e_str)를 파라미터에 직접 대입
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': lh_s_str, 'tndrbidRegDtEnd': lh_e_str, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=15)
            res_lh.encoding = res_lh.apparent_encoding
            clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    b_no = item.findtext('bidNum')
                    final_list.append({'출처':'LH', '번호':b_no, '공고명':bid_nm, '수요기관':'한국토지주택공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), '지역':'전국', '마감일':format_date_clean(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"})
        except: pass

        # --- 3. 국방부 ---
        status_st.info("📡 [3/5] 국방부 수색 중...")
        d2b_configs = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail', 'c': 'biddocPresentnClosDt'}, {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail', 'c': 'prqudoPresentnClosDt'}]
        for cfg in d2b_configs:
            try:
                p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
                if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': s_date_7, 'prqudoPresentnClosDateEnd': target_end_day})
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, headers=HEADERS).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in KEYWORDS):
                        p_no, d_year, d_no = str(it.get('pblancNo', '')), str(it.get('demandYear', '')), str(it.get('dcsNo', ''))
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': p_no, 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': d_year, 'orntCode': it.get('orntCode'), 'dcsNo': d_no, '_type': 'json'}
                        if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        budget, area = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0, "국방부상세"
                        try:
                            det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                            if det: area, budget, p_no = det.get('areaLmttList') or area, det.get('budgetAmount') or budget, det.get('g2bPblancNo') or p_no
                        except: pass
                        if any(t in area for t in MUST_PASS_AREAS):
                            final_list.append({'출처': f"D2B({cfg['t']})", '번호': p_no, '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': area, '마감일': format_date_clean(it.get(cfg['c'])), 'URL': 'https://www.d2b.go.kr'})
            except: continue

        # --- 4. 수자원공사 ---
        status_st.info("📡 [4/5] K-water 수색 중...")
        for kw in KWATER_KEYWORDS:
            try:
                res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", params={'serviceKey': SERVICE_KEY, 'searchDt': search_month, 'bidNm': kw, '_type': 'json'}, timeout=10).json()
                k_items = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for kit in ([k_items] if isinstance(k_items, dict) else k_items):
                    final_list.append({'출처': 'K-water', '번호': kit.get('tndrPbanno'), '공고명': kit.get('tndrPblancNm'), '수요기관': '수자원공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(kit.get('tndrPblancEnddt')), 'URL': f"{KWATER_DETAIL_BASE}{kit.get('tndrPbanno')}"})
            except: continue

        # --- 5. 가스공사 ---
        status_st.info("📡 [5/5] KOGAS 수색 중...")
        try:
            res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': kogas_start}, timeout=15)
            root_kg = ET.fromstring(res_kg.text)
            for item in root_kg.findall('.//item'):
                title = item.findtext('NOTICE_NAME') or '-'
                if any(kw in title for kw in KOGAS_KEYWORDS):
                    final_list.append({'출처': 'KOGAS', '번호': item.findtext('NOTICE_CODE') or '-', '공고명': title, '수요기관': '가스공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(item.findtext('END_DT')), 'URL': KOGAS_HOME})
        except: pass

        # --- [최종 출력] ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 작전 완료! LH 포함 총 {len(df)}건 확보.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='RADAR_REPORT')
            st.download_button(label="📥 통합 리포트(Excel) 저장", data=output.getvalue(), file_name=f"RADAR_FINAL_{today_str}.xlsx")
        else:
            st.warning("⚠️ 포착된 공고가 없습니다. 기간을 확인해 보세요.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
