import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re

# --- [1] 커스텀 세팅 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류"]
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [3] 웹 화면 구성 ---
st.set_page_config(page_title="3사 통합 레이더 최종본", layout="wide")
st.title("🚀 공고검색")

if st.sidebar.button("📡 전 구역 정밀 수색", type="primary"):
    final_list = []
    now = datetime.now()
    s_date, today = (now - timedelta(days=5)).strftime("%Y%m%d"), now.strftime("%Y%m%d")
    
    status = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 ---
        status.info("📡 [1단계] 나라장터 수집 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / (len(KEYWORDS) * 3))
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date+'0000', 'inqryEndDt': today+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    b_no, b_ord = it.get('bidNtceNo'), str(it.get('bidNtceOrd', '0')).zfill(2)
                    try:
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

        # --- 2. LH ---
        status.info("📡 [2단계] LH포털 수집 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            res_lh = requests.get(url_lh, params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today}, timeout=10)
            res_lh.encoding = res_lh.apparent_encoding
            root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text))
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    b_no = item.findtext('bidNum')
                    final_list.append({'출처':'3.LH', '번호':b_no, '공고명':bid_nm, '수요기관':'한국토지주택공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt'), errors='coerce') or 0), '지역':'전국/상세참조', '마감일':format_date_clean(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"})
        except: pass

        # --- 3. 국방부 (부장님 오더대로 budgetAmount 정밀 수집) ---
        status.info("📡 [3단계] 국방부(D2B) 예산 수립 중...")
        for op in ['getDmstcCmpetBidPblancList', 'getDmstcOthbcVltrnNtatPlanList']:
            try:
                url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{op}"
                res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, headers=HEADERS).json()
                items = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in KEYWORDS):
                        # 🎯 국방부 상세 조회를 위해 공고번호 확보
                        p_no = it.get('pblancNo') or it.get('dcsNo') or it.get('othbcNtatNo')
                        budget = 0
                        
                        try:
                            # 상세 조회 API 주소 (List를 Detail로 교체)
                            url_det = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{op.replace('List', 'Detail')}"
                            # 🎯 부장님, 국방부는 pblancNo라는 이름으로 번호를 보내야 상세정보를 줍니다!
                            p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': p_no, '_type': 'json'}
                            det_res = requests.get(url_det, params=p_det, headers=HEADERS, timeout=3).json()
                            det = det_res.get('response', {}).get('body', {}).get('item', {})
                            
                            # 🎯 부장님 지시사항: budgetAmount가 정답!
                            if det:
                                budget = det.get('budgetAmount') or 0
                        except:
                            # 상세 조회 실패 시 목록에 있는 배정예산이라도 가져옴
                            budget = it.get('asignBdgtAmt') or 0
                        
                        final_list.append({
                            '출처':'2.국방부', '번호':p_no, '공고명':bid_nm, '수요기관':it.get('ornt') or "국방부", 
                            '예산':int(pd.to_numeric(budget, errors='coerce') or 0), 
                            '지역':'국방부상세', '마감일':format_date_clean(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')), 
                            'URL':'https://www.d2b.go.kr'
                        })
            except: continue

        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['출처', '마감일'])
            df['출처'] = df['출처'].str.replace(r'^[0-9]\.', '', regex=True)
            st.success(f"✅ 작전 완료! {len(df)}건 확보.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='통합공고')
                workbook, worksheet = writer.book, writer.sheets['통합공고']
                worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
                for i, _ in enumerate(df.columns): worksheet.set_column(i, i, 18)
            st.download_button(label="📥 통합 리포트(Excel) 다운로드", data=output.getvalue(), file_name=f"3사_통합_리포트_{today}.xlsx")
        else:
            status.warning("⚠️ 검색 결과가 없습니다.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
