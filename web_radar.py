import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import io
import re

# --- [1] 부장님 정예 설정 (v161/v169 원본 100% 반영) ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "잔재물", "매립", "재활용"]
TARGET_AREAS = ["경기도", "평택", "화성", "서울", "인천", "전국", "제한없음"]

def clean_date(val):
    if not val: return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) >= 8 else val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v5400", layout="wide")
st.title("📡 THE RADAR v5400.0 (LH & 국방부 전용)")
st.info("🎯 부장님 v161/v169 로직 동기화: LH(CDATA 제거) + 국방부(3중 예산 엔진)")

if st.sidebar.button("🚀 LH/국방부 집중 수색 개시", type="primary"):
    final_list = []
    now = datetime.now()
    
    # 🎯 [기관별 맞춤 날짜 언어]
    lh_start = (now - timedelta(days=7)).strftime("%Y%m%d")
    lh_end = now.strftime("%Y%m%d")
    d2b_start = (now - timedelta(days=10)).strftime("%Y%m%d")
    d2b_future = (now + timedelta(days=10)).strftime("%Y%m%d")

    status_st = st.empty()

    # --- 1. LH (e-Bid) : CDATA 제거 언어 적용 ---
    status_st.info("📡 [LH포털] CDATA 불순물 제거 및 8자리 수색 중...")
    try:
        url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
        p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': lh_start, 'tndrbidRegDtEnd': lh_end, 'cstrtnJobGb': '1'}
        res_lh = requests.get(url_lh, params=p_lh, timeout=15)
        res_lh.encoding = res_lh.apparent_encoding
        
        # 🎯 부장님 필살기: CDATA 제거 후 XML 파싱
        clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        
        for item in root.findall('.//item'):
            bid_nm_raw = item.findtext('bidnmKor', '')
            bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', bid_nm_raw).strip()
            
            if any(kw in bid_nm for kw in KEYWORDS):
                final_list.append({
                    '출처': 'LH',
                    '번호': item.findtext('bidNum'),
                    '공고명': bid_nm,
                    '수요기관': '한국토지주택공사',
                    '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                    '지역': '전국/공고참조',
                    '마감일': clean_date(item.findtext('openDtm')),
                    'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                })
    except: pass

    # --- 2. 국방부 (D2B) : v161 3중 예산 엔진 적용 ---
    status_st.info("📡 [국방부] v161 일반+수의 통합 엔진 가동 중...")
    d2b_configs = [
        {'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail', 'c': 'biddocPresentnClosDt'},
        {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail', 'c': 'prqudoPresentnClosDt'}
    ]
    
    for cfg in d2b_configs:
        try:
            p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}
            if cfg['t'] == '수의':
                p_d.update({'prqudoPresentnClosDateBegin': d2b_start, 'prqudoPresentnClosDateEnd': d2b_future})
            
            res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, headers=HEADERS, timeout=15).json()
            items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            items_d = [items_d] if isinstance(items_d, dict) else items_d
            
            for it in items_d:
                bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                if any(kw in bid_nm for kw in KEYWORDS):
                    # 🎯 부장님 v161 전용: 예산 3중 필터 로직
                    budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                    area = "상세확인"
                    p_no = it.get('pblancNo') or it.get('dcsNo')

                    try:
                        # 상세 정보 보강
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        
                        det_res = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=5).json()
                        det_item = det_res.get('response', {}).get('body', {}).get('item', {})
                        if det_item:
                            budget = det_item.get('budgetAmount') or budget
                            area = det_item.get('areaLmttList') or area
                            p_no = det_item.get('g2bPblancNo') or p_no
                    except: pass

                    if any(t in area for t in TARGET_AREAS):
                        final_list.append({
                            '출처': f"D2B({cfg['t']})",
                            '번호': p_no,
                            '공고명': bid_nm,
                            '수요기관': it.get('ornt'),
                            '예산': int(pd.to_numeric(budget, errors='coerce') or 0),
                            '지역': area,
                            '마감일': clean_date(it.get(cfg['c'])),
                            'URL': 'https://www.d2b.go.kr'
                        })
        except: pass

    status_st.empty()
    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
        st.success(f"✅ 작전 완료! LH와 국방부에서 총 {len(df)}건을 확보했습니다.")
        st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button(label="📥 LH/국방부 통합 리포트 저장", data=output.getvalue(), file_name=f"RADAR_D2B_LH_{lh_end}.xlsx")
    else:
        st.warning("🚨 LH와 국방부 서버 응답은 정상이나, 현재 조건에 맞는 공고가 없습니다.")
