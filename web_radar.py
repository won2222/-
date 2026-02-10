import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re

# --- [1] 부장님 커스텀 세팅 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "나무", "벌채", "뿌리", "폐가구", "대형", "적환장"]
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 웹 화면 구성 ---
st.set_page_config(page_title="3사 통합 레이더 v287", layout="wide")
st.title("🚀 공고검색 (최근 4일 수집 & 국방부 3일 마감)")

if st.sidebar.button("📡 전 구역 정밀 수색 시작", type="primary"):
    final_list = []
    now = datetime.now()
    
    # 🎯 검색 기간 동기화 (나라장터/LH: 최근 4일간 등록된 공고)
    s_date = (now - timedelta(days=4)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    
    # 🎯 국방부 오더: 일반입찰 마감일을 오늘+3일로 타이트하게 제한
    target_end_day = (now + timedelta(days=3)).strftime("%Y%m%d")
    
    status = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 (G2B) - 면허 필터링 포함 ---
        status.info(f"📡 [1단계] 나라장터 수색 중 ({s_date} ~ {today_str})")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / 60) 
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                    try:
                        # 면허 교차 검증 (1226, 1227, 6786, 6770)
                        l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                        lic_items = l_res.get('response', {}).get('body', {}).get('items', [])
                        lic_val = " / ".join(list(set([li.get('lcnsLmtNm','') for li in (lic_items if isinstance(lic_items, list) else [lic_items]) if li.get('lcnsLmtNm')]))) or "공고참조"
                        
                        r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                        reg_items = r_res.get('response', {}).get('body', {}).get('items', [])
                        reg_val = ", ".join(list(set([ri.get('prtcptPsblRgnNm','') for ri in (reg_items if isinstance(reg_items, list) else [reg_items]) if ri.get('prtcptPsblRgnNm')]))) or "전국"
                        
                        if (any(code in lic_val for code in OUR_LICENSES) or "공고참조" in lic_val) and any(ok in reg_val for ok in MUST_PASS_AREAS):
                            final_list.append({'출처':'1.나라장터', '번호':b_no, '공고명':it['bidNtceNm'], '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역':reg_val, '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
                    except: continue
            except: continue

        # --- 2. LH (시설공사 정밀 로직 + 4일 전 동기화) ---
        status.info(f"📡 [2단계] LH 시설공사 수색 중 ({s_date} ~ {today_str})")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'pageNo': '1', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=15)
            res_lh.encoding = res_lh.apparent_encoding
            clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
            root = ET.fromstring(f"<root>{clean_xml}</root>")
            for item in root.findall('.//item'):
                raw_nm = item.findtext('bidnmKor', '')
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', raw_nm).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    b_no = item.findtext('bidNum')
                    final_list.append({'출처':'3.LH', '번호':b_no, '공고명':bid_nm, '수요기관':'한국토지주택공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), '지역':'전국/상세참조', '마감일':format_date_clean(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"})
        except: pass

        # --- 3. 국방부 (v169 수의계약 예산 복구 + 3일 마감 로직) ---
        status.info(f"📡 [3단계] 방위사업청 정밀 수색 중 (마감 3일 이내)")
        d2b_configs = [
            {'type': 'bid', 'op': 'getDmstcCmpetBidPblancList', 'det': 'getDmstcCmpetBidPblancDetail', 'clos': 'biddocPresentnClosDt'},
            {'type': 'priv', 'op': 'getDmstcOthbcVltrnNtatPlanList', 'det': 'getDmstcOthbcVltrnNtatPlanDetail', 'clos': 'prqudoPresentnClosDt'}
        ]
        for config in d2b_configs:
            try:
                url_list = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{config['op']}"
                res_d = requests.get(url_list, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, headers=HEADERS).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = it.get(config['clos'])
                    
                    # 🎯 부장님 필터: 키워드 확인 & (일반입찰은 3일 이내 마감 건만 / 수의계약은 전체)
                    if any(kw in bid_nm for kw in KEYWORDS) and (config['type']=='priv' or (today_str <= str(clos_dt)[:8] <= target_end_day)):
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'), 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if config['type'] == 'priv':
                            p_det.update({'iemNo': it.get('iemNo'), 'ntatPlanDate': it.get('ntatPlanDate')})
                        
                        budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                        try:
                            url_det = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{config['det']}"
                            det_res = requests.get(url_det, params=p_det, headers=HEADERS, timeout=5).json()
                            det_item = det_res.get('response', {}).get('body', {}).get('item', {})
                            budget = det_item.get('budgetAmount') or budget
                        except: pass
                        
                        final_list.append({'출처':'2.국방부', '번호':it.get('pblancNo') or it.get('dcsNo'), '공고명':bid_nm, '수요기관':it.get('ornt') or "국방부", '예산':int(pd.to_numeric(budget, errors='coerce') or 0), '지역':'국방부상세', '마감일':format_date_clean(clos_dt), 'URL':'https://www.d2b.go.kr'})
            except: continue

        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['출처', '마감일'])
            df['출처'] = df['출처'].str.replace(r'^[0-9]\.', '', regex=True)
            st.success(f"✅ 작전 완료! {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='통합공고')
                workbook, worksheet = writer.book, writer.sheets['통합공고']
                worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
                for i, _ in enumerate(df.columns): worksheet.set_column(i, i, 20)
            st.download_button(label="📥 통합 리포트(Excel) 다운로드", data=output.getvalue(), file_name=f"3사_통합_{today_str}.xlsx")
        else:
            status.warning("⚠️ 최근 조건에 맞는 공고가 없습니다.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
