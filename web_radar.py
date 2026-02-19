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

# 🎯 키워드 전략 (부장님 오더)
G2B_KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
CORE_KEYWORDS = ["폐기물", "폐목재", "식물성", "낙엽", "임목", "가연성", "폐가구", "초본류", "부유물"]

# 🎯 지역 필터 (서울, 인천 제외 / 경기, 평택, 화성, 전국 집중)
MUST_PASS_AREAS = ['경기', '경기도', '평택', '평택시', '화성', '화성시', '전국', '제한없음']
OUR_LICENSES = ['1226', '1227', '6786', '6770']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v1800", layout="wide")
st.title("📡 THE RADAR v1800.0")
st.info("💡 정확한 수색을 위해 시간이 다소 소요될 수 있습니다. (서울·인천 제외 모드)")
st.divider()

# 수색 기간 설정
KST = pytz.timezone('Asia/Seoul')
now = datetime.now(KST)
s_date = (now - timedelta(days=7)).strftime("%Y%m%d")
today_str = now.strftime("%Y%m%d")
target_end_day = (now + timedelta(days=10)).strftime("%Y%m%d")
search_month = now.strftime('%Y%m')

if st.sidebar.button("🚀 정밀 통합 수색 개시", type="primary"):
    final_list = []
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 🎯 1. LH (독립 엔진 - XML 강제 세척) ---
        status_st.info("📡 LH 시설공사 수색 중... (XML 세척 중)")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            # 부장님이 성공하셨던 pageNo=1, numOfRows=500 설정 유지
            p_lh = {'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=30)
            res_lh.encoding = res_lh.apparent_encoding
            # CDATA 및 특수문자 제거 로직 강화
            lh_raw = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
            root = ET.fromstring(f"<root>{lh_raw}</root>")
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in CORE_KEYWORDS):
                    final_list.append({
                        '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm,
                        '수요기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                        '지역': '전국/공고참조', '마감일': format_date_clean(item.findtext('openDtm')),
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
        except: pass
        prog.progress(20)

        # --- 🎯 2. 나라장터 (정밀 면허/지역 2차 필터링) ---
        status_st.info("📡 나라장터 18종 키워드 순회 중... (면허/지역 검증)")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for kw in G2B_KEYWORDS:
            try:
                time.sleep(0.1) # 서버 부하 방지
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=10).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                for it in ([items] if isinstance(items, dict) else items):
                    b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                    # 면허/지역 데이터 확보 (v169 로직)
                    l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                    lic_items = str(l_res.get('response', {}).get('body', {}).get('items', []))
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                    reg_items = str(r_res.get('response', {}).get('body', {}).get('items', []))
                    
                    # 면허/지역 정밀 매칭
                    lic_ok = any(code in lic_items for code in OUR_LICENSES) or "[]" in lic_items
                    reg_ok = any(area in reg_items for area in MUST_PASS_AREAS)
                    
                    if lic_ok and reg_ok:
                        final_list.append({
                            '출처': 'G2B', '번호': b_no, '공고명': it.get('bidNtceNm'), '수요기관': it.get('dminsttNm'),
                            '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역': reg_items[:50], 
                            '마감일': format_date_clean(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')
                        })
            except: continue
        prog.progress(50)

        # --- 🎯 3. 국방부 (v161.0 엔진 - 통합참조번호 및 상세 파싱) ---
        status_st.info("📡 국방부 상세 정보 추적 중... (unityRefNo 추출)")
        d2b_configs = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail'}, 
                       {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail'}]
        for cfg in d2b_configs:
            try:
                p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
                if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': today_str, 'prqudoPresentnClosDateEnd': target_end_day})
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, timeout=20).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for it in ([items_d] if isinstance(items_d, dict) else items_d):
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in CORE_KEYWORDS):
                        # 상세 페이지 침투
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        try:
                            det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                            area = det.get('areaLmttList') or "상세확인"
                            # 서울/인천 제외 로직 (MUST_PASS_AREAS에 경기권만 있음)
                            if any(t in area for t in MUST_PASS_AREAS):
                                final_list.append({
                                    '출처': f'D2B({cfg["t"]})', '번호': det.get('g2bPblancNo') or it.get('pblancNo'),
                                    '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(det.get('budgetAmount') or it.get('asignBdgtAmt') or 0)),
                                    '지역': area, '마감일': format_date_clean(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'
                                })
                        except: pass
            except: continue
        prog.progress(80)

        # --- 🎯 4. 수자원공사 (정밀 키워드 필터링 보강) ---
        status_st.info("📡 수자원공사 정밀 수색 중...")
        try:
            res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", params={'serviceKey': SERVICE_KEY, 'searchDt': search_month, '_type': 'json'}, timeout=15).json()
            k_items = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            for kit in ([k_items] if isinstance(k_items, dict) else k_items):
                title = kit.get('tndrPblancNm', '')
                # 🎯 필터링 보강: 가져온 뒤 부장님 핵심 키워드로 재검증
                if any(kw in title for kw in CORE_KEYWORDS):
                    final_list.append({
                        '출처': 'K-water', '번호': kit.get('tndrPbanno'), '공고명': title,
                        '수요기관': '한국수자원공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(kit.get('tndrPblancEnddt')),
                        'URL': f"https://ebid.kwater.or.kr/wq/index.do?tndrPbanno={kit.get('tndrPbanno')}"
                    })
        except: pass
        prog.progress(100)

        # --- [결과 출력] ---
        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 작전 성공! 총 {len(df)}건을 확보했습니다. (서울·인천 제외)")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 전략 리포트 저장", data=output.getvalue(), file_name=f"RADAR_FILTERED_{today_str}.xlsx")
        else:
            st.warning("⚠️ 현재 필터 조건에 부합하는 공고가 없습니다.")
            
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
