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

# --- [1] 글로벌 설정 및 부장님 정예 키워드 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v2400", layout="wide")
st.title("📡 THE RADAR v2400.0")
st.caption("v161.0 정밀 로직 기반 - 국방부 SCU & 나라장터 면허 필터 복구")
st.divider()

# 시간 설정 (KST 7일 고정)
KST = pytz.timezone('Asia/Seoul')
now = datetime.now(KST)
s_date = (now - timedelta(days=7)).strftime("%Y%m%d")
today_str = now.strftime("%Y%m%d")
search_month = now.strftime('%Y%m')
target_end_day = (now + timedelta(days=7)).strftime("%Y%m%d")

if st.sidebar.button("🔍 전 채널 정밀 수색 개시", type="primary"):
    final_list = []
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 🎯 1. 나라장터 (G2B) 독립 엔진 ---
        status_st.info("📡 [1/5] 나라장터 수색 중... (면허/지역 2차 검증)")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / (len(KEYWORDS) * 2))
            try:
                time.sleep(0.1) # 서버 과부하 방지
                # 부장님 로직 날짜 규격 적용
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=10).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                
                for it in ([items] if isinstance(items, dict) else items):
                    if "전자입찰" not in it.get('bidMethdNm', ''): continue
                    b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                    
                    # 면허/지역 2차 검증 (v161 정예 로직)
                    l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                    lic_items = l_res.get('response', {}).get('body', {}).get('items', [])
                    lic_val = " / ".join(list(set([li.get('lcnsLmtNm','') for li in (lic_items if isinstance(lic_items, list) else [lic_items]) if li.get('lcnsLmtNm')]))) or "공고참조"
                    
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}).json()
                    reg_items = r_res.get('response', {}).get('body', {}).get('items', [])
                    reg_val = ", ".join(list(set([ri.get('prtcptPsblRgnNm','') for ri in (reg_items if isinstance(reg_items, list) else [reg_items]) if ri.get('prtcptPsblRgnNm')]))) or "전국"
                    
                    if (any(code in lic_val for code in OUR_LICENSES) or "공고참조" in lic_val) and any(ok in reg_val for ok in MUST_PASS_AREAS):
                        final_list.append({
                            '출처': 'G2B', '번호': b_no, '공고명': it['bidNtceNm'], '수요기관': it['dminsttNm'],
                            '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0),
                            '지역': reg_val, '마감일': format_date_clean(it.get('bidClseDt')), 'URL': it.get('bidNtceDtlUrl')
                        })
            except: continue

        # --- 🎯 2. LH 독립 엔진 ---
        status_st.info("📡 [2/5] LH 시설공사 수색 중... (XML 세척)")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=15)
            res_lh.encoding = res_lh.apparent_encoding
            lh_raw = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
            root = ET.fromstring(f"<root>{lh_raw}</root>")
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    final_list.append({
                        '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm, '수요기관': '한국토지주택공사',
                        '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0),
                        '지역': '전국', '마감일': format_date_clean(item.findtext('openDtm')),
                        'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
        except: pass

        # --- 🎯 3. 국방부 (v161.0 정예 엔진 - SCU 번호 복구) ---
        status_st.info("📡 [3/5] 국방부 정밀 수색 중... (통합참조번호 추출)")
        d2b_cfg = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail'}, 
                    {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail'}]
        for cfg in d2b_cfg:
            try:
                p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
                if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': s_date, 'prqudoPresentnClosDateEnd': target_end_day})
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for it in ([items_d] if isinstance(items_d, dict) else items_d):
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in KEYWORDS):
                        # 상세 API 접속하여 g2bPblancNo(SCU...) 낚아채기
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        
                        try:
                            det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                            area = det.get('areaLmttList') or "상세확인"
                            if any(t in area for t in MUST_PASS_AREAS):
                                final_list.append({
                                    '출처': f'D2B({cfg["t"]})', 
                                    '번호': det.get('g2bPblancNo') or it.get('pblancNo'), # 🎯 SCU 번호 우선
                                    '공고명': bid_nm, '수요기관': it.get('ornt'),
                                    '예산': int(pd.to_numeric(det.get('budgetAmount') or it.get('asignBdgtAmt') or 0)),
                                    '지역': area, '마감일': format_date_clean(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')), 
                                    'URL': 'https://www.d2b.go.kr'
                                })
                        except: pass
            except: continue

        # --- [최종 출력] ---
        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 수색 완료! 총 {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 전략 리포트(Excel) 저장", data=output.getvalue(), file_name=f"RADAR_v2400_{today_str}.xlsx")
        else:
            st.warning("⚠️ 검색 결과가 없습니다. 날짜나 키워드를 확인해 보세요.")
            
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
