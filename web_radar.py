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
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류"]
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

# --- [2] 유틸리티 함수 ---
def get_safe_date(val):
    if not val: return "00000000"
    s_val = str(val).replace(".0", "").strip()
    return s_val[:8] if len(s_val) >= 8 else "00000000"

def format_date_clean(val):
    if not val or val == "-": return "-"
    date_str = str(val).replace(".0", "")
    try:
        if len(date_str) >= 12: return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {date_str[8:10]}:{date_str[10:12]}"
        elif len(date_str) >= 8: return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str
    except: return date_str

# --- [3] 웹 화면 구성 ---
st.set_page_config(page_title="3사 통합 레이더 Web", layout="wide")
st.title("🚀 전국 3사 통합 공고 레이더")
st.sidebar.header("📊 작전 통제실")

if st.sidebar.button("📡 수색 시작", type="primary"):
    final_list = []
    now = datetime.now()
    s_date_api = (now - timedelta(days=5)).strftime("%Y%m%d")
    today_api = now.strftime("%Y%m%d")
    
    status_msg = st.empty()
    prog_bar = st.progress(0)
    
    try:
        # 1. 나라장터
        status_msg.info("📡 [1단계] 나라장터(G2B) 분석 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog_bar.progress((i + 1) / (len(KEYWORDS) * 3))
            p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date_api+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
            try:
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    b_no, b_ord = it['bidNtceNo'], str(it.get('bidNtceOrd', '0')).zfill(2)
                    try:
                        l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                        lic_val = " / ".join(list(set([li.get('lcnsLmtNm','') for li in l_res.get('response',{}).get('body',{}).get('items',[]) if li.get('lcnsLmtNm')]))) or "공고참조"
                        r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                        reg_val = ", ".join(list(set([ri.get('prtcptPsblRgnNm','') for ri in r_res.get('response',{}).get('body',{}).get('items',[]) if ri.get('prtcptPsblRgnNm')]))) or "전국"
                        if (any(code in lic_val for code in OUR_LICENSES) or lic_val == "공고참조") and any(ok in reg_val for ok in MUST_PASS_AREAS):
                            final_list.append({'출처':'나라장터', '번호':b_no, '공고명':it['bidNtceNm'], '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역':reg_val, '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
                    except: continue
            except: continue

        # 2. LH
        status_msg.info("📡 [2단계] LH포털 수집 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            res_lh = requests.get(url_lh, params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'pageNo': '1', 'tndrbidRegDtStart': s_date_api, 'tndrbidRegDtEnd': today_api}, timeout=10)
            res_lh.encoding = res_lh.apparent_encoding
            root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text))
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    b_no = item.findtext('bidNum')
                    final_list.append({'출처':'LH', '번호':b_no, '공고명':bid_nm, '수요기관':'한국토지주택공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt'), errors='coerce') or 0), '지역':'전국/상세참조', '마감일':format_date_clean(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"})
        except: pass

        # 3. 국방부 (수정 완료!)
        status_msg.info("📡 [3단계] 국방부(D2B) 정밀 수색 중...")
        for op in ['getDmstcCmpetBidPblancList', 'getDmstcOthbcVltrnNtatPlanList']:
            try:
                url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{op}"
                res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, headers=HEADERS).json()
                items = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items = [items] if isinstance(items, dict) else items
                for it in items:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = get_safe_date(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt'))
                    if any(kw in bid_nm for kw in KEYWORDS):
                        try:
                            # 🎯 url_det 명칭 통일 및 호출 수정
                            url_det = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{op.replace('List', 'Detail')}"
                            p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), '_type': 'json'}
                            det_res = requests.get(url_det, params=p_det, headers=HEADERS, timeout=5).json()
                            det = det_res.get('response', {}).get('body', {}).get('item', {})
                            
                            budget = int(pd.to_numeric(det.get('budgetAmount') or it.get('asignBdgtAmt') or 0, errors='coerce') or 0)
                            final_list.append({'출처':'국방부', '번호':it.get('pblancNo') or it.get('dcsNo'), '공고명':bid_nm, '수요기관':it.get('ornt'), '예산':budget, '지역':det.get('areaLmttList') or "제한없음", '마감일':format_date_clean(clos_dt), 'URL':'https://www.d2b.go.kr'})
                        except: pass
            except: pass

        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by='마감일')
            status_msg.success(f"✅ 작전 완료! 총 {len(df)}건을 확보했습니다.")
            st.dataframe(df, use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='통합공고')
            st.download_button(label="📥 엑셀 파일 다운로드", data=output.getvalue(), file_name=f"report_{today_api}.xlsx")
        else:
            status_msg.warning("⚠️ 검색 결과가 없습니다.")

    except Exception as e:
        st.error(f"🚨 오류 발생: {e}")
