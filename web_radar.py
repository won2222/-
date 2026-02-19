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

# --- [1] 부장님 v161.0 기반 정예 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "임목", "폐가구", "대형", "적환장"]
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v1600", layout="wide")
st.title("📡 THE RADAR v1600.0")
st.caption("v161.0 국방부 통합참조번호 엔진 & 면허정보 가시화")
st.divider()

# 수색 기간 정보 (7일 고정)
KST = pytz.timezone('Asia/Seoul')
now = datetime.now(KST)
s_date = (now - timedelta(days=7)).strftime("%Y%m%d")
today_str = now.strftime("%Y%m%d")
target_end_day = (now + timedelta(days=7)).strftime("%Y%m%d")

if st.sidebar.button("🔍 전 기관 정밀 수색 개시", type="primary"):
    final_list = []
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 🎯 1. 나라장터 (G2B) - 면허정보 노출 보강 ---
        status_st.info("📡 [1/3] 나라장터 수색 및 면허 데이터 추출 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / 100)
            try:
                time.sleep(0.05)
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                    try:
                        # 면허 정보 상세 수집
                        l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                        lic_items = l_res.get('response', {}).get('body', {}).get('items', [])
                        lic_val = " / ".join(list(set([li.get('lcnsLmtNm','') for li in (lic_items if isinstance(lic_items, list) else [lic_items]) if li.get('lcnsLmtNm')]))) or "공고참조"
                        
                        r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                        reg_val = ", ".join(list(set([ri.get('prtcptPsblRgnNm','') for ri in (r_res.get('response', {}).get('body', {}).get('items', [])) if ri.get('prtcptPsblRgnNm')]))) or "전국"
                        
                        if (any(code in lic_val for code in OUR_LICENSES) or "공고참조" in lic_val) and any(ok in reg_val for ok in MUST_PASS_AREAS):
                            final_list.append({'출처':'G2B', '번호':b_no, '공고명':it['bidNtceNm'], '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역':reg_val, '면허정보': lic_val, '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
                    except: continue
            except: continue

        # --- 🎯 2. LH ---
        status_st.info("📡 [2/3] LH 수색 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, timeout=15)
            res_lh.encoding = res_lh.apparent_encoding
            clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    b_no = item.findtext('bidNum')
                    final_list.append({'출처':'LH', '번호':b_no, '공고명':bid_nm, '수요기관':'한국토지주택공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), '지역':'전국', '면허정보': '상세참조', '마감일':format_date_clean(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}"})
        except: pass

        # --- 🎯 3. 국방부 (부장님 v161.0 엔진 완벽 이식) ---
        status_st.info("📡 [3/3] 국방부 통합참조번호(SCU) 및 예산 정밀 수색 중...")
        d2b_cfg = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail', 'c': 'biddocPresentnClosDt'}, {'t': '공개수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail', 'c': 'prqudoPresentnClosDt'}]
        for cfg in d2b_cfg:
            p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
            if cfg['t'] == '공개수의': p_d.update({'prqudoPresentnClosDateBegin': s_date, 'prqudoPresentnClosDateEnd': target_end_day})
            try:
                res_d = requests.get(cfg['l'], params=p_d).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in KEYWORDS):
                        # 부장님 v161.0 조합 로직
                        p_no, d_year, d_no = it.get('pblancNo'), str(it.get('demandYear', '')), str(it.get('dcsNo', ''))
                        p_prefix = "".join([c for c in p_no if c.isalpha()]) if p_no else ""
                        unity_ref_no = f"{d_year}{p_prefix}{d_no}" # 기본값 세팅
                        
                        # 상세 API 접속 (예산 및 통합참조번호 확보)
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': p_no, 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': d_year, 'orntCode': it.get('orntCode'), 'dcsNo': d_no, '_type': 'json'}
                        if cfg['t'] == '공개수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        
                        area, budget = "상세확인", 0
                        try:
                            det_res = requests.get(cfg['d'], params=p_det, timeout=5).json()
                            det_data = det_res.get('response', {}).get('body', {}).get('item', {})
                            if det_data:
                                area = det_data.get('areaLmttList') or "제한없음"
                                # 🎯 [핵심] 통합참조번호(G2B번호) 추출
                                unity_ref_no = det_data.get('g2bPblancNo') or unity_ref_no
                                budget = det_data.get('budgetAmount') or it.get('asignBdgtAmt') or 0
                        except: pass
                        
                        if any(t in area for t in MUST_PASS_AREAS):
                            final_list.append({'출처': f"D2B({cfg['t']})", '번호': unity_ref_no, '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': area, '면허정보': '상세확인', '마감일': format_date_clean(it.get(cfg['c'])), 'URL': 'https://www.d2b.go.kr'})
            except: continue

        # --- [최종 결과] ---
        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 수색 완료! 총 {len(df)}건 확보.")
            # 면허정보 컬럼을 공고명 옆으로 배치
            cols = ['출처', '번호', '공고명', '면허정보', '수요기관', '예산', '지역', '마감일', 'URL']
            st.dataframe(df[cols].style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 전략 리포트(Excel) 저장", data=output.getvalue(), file_name=f"RADAR_v1600_{today_str}.xlsx")
        else:
            st.warning("⚠️ 검색 조건에 맞는 공고가 없습니다.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")

