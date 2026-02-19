import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
import io
import re
import time
import pytz
from datetime import datetime, timedelta  # 🎯 에러 해결 핵심: 명시적 임포트

# --- [1] 부장님 정예 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 18종 풀 키워드 및 면허 4종
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기', '경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).replace(".0", "").strip())
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v2000", layout="wide")
st.title("📡 THE RADAR v2000.0")
st.info("🎯 나라장터 NameError 해결 및 국방부 수의계약 SCU번호 엔진 통합완료")

# 시간 설정
KST = pytz.timezone('Asia/Seoul')
now = datetime.now(KST)
s_date_str = (now - timedelta(days=7)).strftime("%Y%m%d")
today_str = now.strftime("%Y%m%d")
d2b_future = (now + timedelta(days=20)).strftime("%Y%m%d")

if st.sidebar.button("🚀 전 구역 정밀 수색 개시", type="primary"):
    final_list = []
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 🎯 1. 나라장터 (G2B) - 검색 엔진 완전 복구 ---
        status_st.info("📡 [1/3] 나라장터 18종 키워드 수색 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / (len(KEYWORDS) * 2))
            try:
                time.sleep(0.15) # 서버 차단 방지용 미세 지연
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date_str+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=10).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                
                for it in ([items] if isinstance(items, dict) else items):
                    b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                    
                    # 면허/지역 데이터 상세 확보
                    l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                    lic_str = str(l_res.get('response', {}).get('body', {}).get('items', []))
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                    reg_str = str(r_res.get('response', {}).get('body', {}).get('items', []))
                    
                    # 면허(4종) + 지역(경기/서울/인천/전국) 필터
                    lic_ok = any(code in lic_str for code in OUR_LICENSES) or "[]" in lic_str
                    reg_ok = any(area in reg_str for area in MUST_PASS_AREAS)
                    
                    if lic_ok and reg_ok:
                        final_list.append({
                            '출처': 'G2B', '번호': b_no, '공고명': it.get('bidNtceNm'), '수요기관': it.get('dminsttNm'),
                            '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역': reg_str[:50], '면허정보': lic_str[:50],
                            '마감일': format_date_clean(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')
                        })
            except: continue

        # --- 🎯 2. LH (v169 로직) ---
        status_st.info("📡 [2/3] LH 수색 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            p_lh = {'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 'tndrbidRegDtStart': s_date_str, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=20)
            res_lh.encoding = res_lh.apparent_encoding
            lh_raw = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
            root = ET.fromstring(f"<root>{lh_raw}</root>")
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    final_list.append({'출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm, '수요기관': 'LH공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), '지역': '전국', '면허정보': '상세참조', '마감일': format_date_clean(item.findtext('openDtm')), 'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"})
        except: pass

        # --- 🎯 3. 국방부 (v161.0 엔진 - 수의/일반 통합참조번호) ---
        status_st.info("📡 [3/3] 국방부 정밀 추적 중... (SCU번호 확보)")
        d2b_configs = [
            {'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail'}, 
            {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail'}
        ]
        for cfg in d2b_configs:
            try:
                p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
                if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': s_date_str, 'prqudoPresentnClosDateEnd': d2b_future})
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, timeout=20).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for it in ([items_d] if isinstance(items_d, dict) else items_d):
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in KEYWORDS):
                        # 🎯 v161.0 핵심: 통합참조번호(g2bPblancNo)를 위한 상세 API 침투
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        
                        try:
                            det_res = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=10).json()
                            det = det_res.get('response', {}).get('body', {}).get('item', {})
                            area = det.get('areaLmttList') or "상세확인"
                            
                            # 🎯 수의/일반 모두 SCU... 번호 확보
                            unity_ref_no = det.get('g2bPblancNo') or it.get('pblancNo')
                            
                            if any(t in area for t in MUST_PASS_AREAS):
                                final_list.append({
                                    '출처': f'D2B({cfg["t"]})', '번호': unity_ref_no, '공고명': bid_nm, '수요기관': it.get('ornt'), 
                                    '예산': int(pd.to_numeric(det.get('budgetAmount') or it.get('asignBdgtAmt') or 0)), '지역': area, '면허정보': '상세참조',
                                    '마감일': format_date_clean(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'
                                })
                        except: pass
            except: continue

        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 작전 완료! 나라장터 및 국방부 SCU 번호 등 총 {len(df)}건 확보.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 통합 전략 리포트 저장", data=output.getvalue(), file_name=f"RADAR_v2000_{today_str}.xlsx")
        else:
            st.warning("⚠️ 포착된 공고가 없습니다. 키워드나 범위를 확인해 보세요.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
