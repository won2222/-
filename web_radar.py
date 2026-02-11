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

# --- [1] 부장님 커스텀 세팅 (정예 키워드 및 지역) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]
KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]

OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

# URL 및 기관 설정
KWATER_DETAIL_BASE = "https://ebid.kwater.or.kr/wq/index.do?w2xPath=/ui/index.xml&view=/bidpblanc/bidpblancsttus/BIDBD32000002.xml&tndrPbanno="
KOGAS_HOME = "https://k-ebid.kogas.or.kr"

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 커스텀 디자인 적용 ---
st.set_page_config(page_title="THE RADAR", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;700;900&display=swap');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif; }
    .main-title { font-size: 42px; font-weight: 900; color: #1E3A8A; letter-spacing: -2px; margin-bottom: 0px; }
    .sub-title { font-size: 14px; color: #6B7280; font-weight: 500; margin-bottom: 40px; letter-spacing: 2px; }
    .metric-card { 
        background-color: #F3F4F6; padding: 20px; border-radius: 12px; border-left: 5px solid #1E3A8A; 
        box-shadow: 2px 2px 10px rgba(0,0,0,0.05); text-align: center;
    }
    .metric-val { font-size: 24px; font-weight: 700; color: #1E3A8A; }
    .metric-label { font-size: 12px; color: #4B5563; }
    </style>
    <div class="main-title">📡 THE RADAR</div>
    <div class="sub-title">FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE SYSTEM</div>
    """, unsafe_allow_all_html=True)

if st.sidebar.button("🔍 전략 수색 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 날짜 세팅
    s_date = (now - timedelta(days=4)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    search_month = now.strftime('%Y%m') 
    kogas_start = (now - timedelta(days=14)).strftime("%Y%m%d") # 부장님 오더: 2주
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=3)).strftime("%Y%m%d")
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 ---
        status_st.info("📡 [PHASE 1] G2B 수색 중...")
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

        # --- 2. LH ---
        status_st.info("📡 [PHASE 2] LH 수색 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            res_lh = requests.get(url_lh, params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}, headers=HEADERS, timeout=15)
            root = ET.fromstring(f"<root>{re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()}</root>")
            for item in root.findall('.//item'):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    b_no = item.findtext('bidNum')
                    final_list.append({'출처':'LH', '번호':b_no, '공고명':bid_nm, '수요기관':'LH', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), '지역':'전국', '마감일':format_date_clean(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"})
        except: pass

        # --- 3. 국방부 (v161.0) ---
        status_st.info("📡 [PHASE 3] D2B 수색 중...")
        for cfg in [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail', 'c': 'biddocPresentnClosDt'}, {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail', 'c': 'prqudoPresentnClosDt'}]:
            try:
                p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
                if cfg['t'] == '수의': p_d.update({'prqudoPresentnClosDateBegin': s_date, 'prqudoPresentnClosDateEnd': target_end_day})
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, headers=HEADERS).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt_f = it.get(cfg['c'])
                    clos_dt = str(clos_dt_f)[:8]
                    if any(kw in bid_nm for kw in KEYWORDS) and (cfg['t']=='수의' or (tomorrow_str <= clos_dt <= target_end_day)):
                        p_no, d_year, d_no = str(it.get('pblancNo', '')), str(it.get('demandYear', '')), str(it.get('dcsNo', ''))
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': p_no, 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': d_year, 'orntCode': it.get('orntCode'), 'dcsNo': d_no, '_type': 'json'}
                        if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        budget, area = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0, "상세참조"
                        try:
                            det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                            if det: area, budget, p_no = det.get('areaLmttList') or area, det.get('budgetAmount') or budget, det.get('g2bPblancNo') or p_no
                        except: pass
                        if any(t in area for t in MUST_PASS_AREAS):
                            final_list.append({'출처':f'D2B({cfg["t"]})', '번호':p_no, '공고명':bid_nm, '수요기관':it.get('ornt'), '예산':int(pd.to_numeric(budget, errors='coerce') or 0), '지역':area, '마감일':format_date_clean(clos_dt_f), 'URL':'https://www.d2b.go.kr'})
            except: continue

        # --- 4. 수자원공사 ---
        status_st.info("📡 [PHASE 4] K-water 수색 중...")
        for kw in KWATER_KEYWORDS:
            try:
                res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", params={'serviceKey': SERVICE_KEY, 'searchDt': search_month, 'bidNm': kw, '_type': 'json'}, timeout=10).json()
                k_items = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                k_items = [k_items] if isinstance(k_items, dict) else k_items
                for kit in k_items:
                    title = kit.get('tndrPblancNm', '-')
                    raw_no = kit.get('tndrPbanno', '-')
                    if any(k in title for k in KWATER_KEYWORDS):
                        final_list.append({'출처': 'K-water', '번호': raw_no, '공고명': title, '수요기관': '수자원공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(kit.get('tndrPblancEnddt')), 'URL': f"{KWATER_DETAIL_BASE}{raw_no}"})
            except: continue

        # --- 5. 가스공사 ---
        status_st.info("📡 [PHASE 5] KOGAS 수색 중...")
        try:
            res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': kogas_start}, timeout=15)
            root_kg = ET.fromstring(res_kg.text)
            for item in root_kg.findall('.//item'):
                title = item.findtext('NOTICE_NAME') or '-'
                if any(kw in title for kw in KOGAS_KEYWORDS):
                    final_list.append({'출처': 'KOGAS', '번호': item.findtext('NOTICE_CODE') or '-', '공고명': title, '수요기관': '가스공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(item.findtext('END_DT')), 'URL': KOGAS_HOME})
        except: pass

        # --- [대시보드 출력] ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            
            # 상단 현황 카드
            c1, c2, c3, c4, c5 = st.columns(5)
            counts = df['출처'].value_counts()
            with c1: st.markdown(f'<div class="metric-card"><div class="metric-label">나라장터</div><div class="metric-val">{counts.get("G2B",0)}</div></div>', unsafe_allow_all_html=True)
            with c2: st.markdown(f'<div class="metric-card"><div class="metric-label">LH</div><div class="metric-val">{counts.get("LH",0)}</div></div>', unsafe_allow_all_html=True)
            with c3: st.markdown(f'<div class="metric-card"><div class="metric-label">국방부</div><div class="metric-val">{counts.get("D2B(일반)",0)+counts.get("D2B(수의)",0)}</div></div>', unsafe_allow_all_html=True)
            with c4: st.markdown(f'<div class="metric-card"><div class="metric-label">수자원</div><div class="metric-val">{counts.get("K-water",0)}</div></div>', unsafe_allow_all_html=True)
            with c5: st.markdown(f'<div class="metric-card"><div class="metric-label">가스공사</div><div class="metric-val">{counts.get("KOGAS",0)}</div></div>', unsafe_allow_all_html=True)
            
            st.write("")
            st.success(f"✅ 총 {len(df)}건의 전략 공고가 포착되었습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            # 엑셀 다운로드 (부장님 파란색 서식)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='RADAR_REPORT')
                workbook, worksheet = writer.book, writer.sheets['RADAR_REPORT']
                h_fmt = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#1E3A8A', 'border': 1, 'align': 'center'})
                b_fmt = workbook.add_format({'border': 1, 'align': 'left'})
                n_fmt = workbook.add_format({'border': 1, 'align': 'right', 'num_format': '#,##0원'})
                for c_idx, val in enumerate(df.columns.values): worksheet.write(0, c_idx, val, h_fmt)
                worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
                for i, col in enumerate(df.columns):
                    width = 50 if col == '공고명' else 20
                    fmt = n_fmt if col == '예산' else b_fmt
                    worksheet.set_column(i, i, width, fmt)
            st.download_button(label="📥 전략 리포트(Excel) 다운로드", data=output.getvalue(), file_name=f"RADAR_{today_str}.xlsx")
        else:
            st.warning("⚠️ 현재 조건에 부합하는 공고가 없습니다.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
