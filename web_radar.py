import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import time
# 🎯 서버와 상관없이 한국 시간을 잡기 위한 설정
import pytz 

# --- [1] 커스텀 세팅 (부장님 15종 키워드) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 웹 화면 구성 ---
st.set_page_config(page_title="3사 통합 레이더 v291", layout="wide")
st.title("🚀 공고검색 (한국 시간 동기화 및 v161.0 적용)")

if st.sidebar.button("📡 전 구역 정밀 수색 시작", type="primary"):
    final_list = []
    
    # 🎯 서버 시간 무시, 한국 시간 강제 고정
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 나라장터/LH 검색 기준 (최근 4일)
    s_date = (now - timedelta(days=4)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    
    # 국방부 마감일 필터 (내일부터 3일간)
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=3)).strftime("%Y%m%d")
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. 나라장터 (G2B) ---
        status_st.info(f"📡 [1단계] 나라장터 수집 ({s_date} ~ {today_str})")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for i, kw in enumerate(KEYWORDS):
            prog.progress((i + 1) / 60)
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
                            final_list.append({'출처':'1.나라장터', '번호':b_no, '공고명':it['bidNtceNm'], '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역':reg_val, '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
                    except: continue
            except: continue

        # --- 2. LH ---
        status_st.info(f"📡 [2단계] LH 시설공사 수집 ({s_date} ~ {today_str})")
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

        # --- 3. 국방부 (v161.0 정밀 로직) ---
        status_st.info(f"📡 [3단계] 방위사업청 v161.0 수색 ({tomorrow_str} ~ {target_end_day})")
        api_configs = [
            {'type': '일반입찰', 'list': 'getDmstcCmpetBidPblancList', 'det': 'getDmstcCmpetBidPblancDetail', 'clos': 'biddocPresentnClosDt'},
            {'type': '공개수의', 'list': 'getDmstcOthbcVltrnNtatPlanList', 'det': 'getDmstcOthbcVltrnNtatPlanDetail', 'clos': 'prqudoPresentnClosDt'}
        ]
        for config in api_configs:
            url_list = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{config['list']}"
            params_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
            if config['type'] == '공개수의': params_d.update({'prqudoPresentnClosDateBegin': s_date, 'prqudoPresentnClosDateEnd': target_end_day})
            try:
                res_d = requests.get(url_list, params=params_d, headers=HEADERS).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                for it in items_d:
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt_full = it.get(config['clos'])
                    clos_dt = str(clos_dt_full)[:8]
                    if any(kw in bid_nm for kw in KEYWORDS):
                        if config['type'] == '공개수의' or (tomorrow_str <= clos_dt <= target_end_day):
                            p_no, d_year, d_no = str(it.get('pblancNo', '')), str(it.get('demandYear', '')), str(it.get('dcsNo', ''))
                            p_prefix = "".join([c for c in p_no if c.isalpha()])
                            combined_no = f"{d_year}{p_prefix}{d_no}"
                            p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': p_no, 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': d_year, 'orntCode': it.get('orntCode'), 'dcsNo': d_no, '_type': 'json'}
                            if config['type'] == '공개수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                            area, budget = "국방부상세", it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                            try:
                                url_det = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{config['det']}"
                                det_data = requests.get(url_det, params=p_det, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                                if det_data:
                                    area = det_data.get('areaLmttList') or area
                                    combined_no = det_data.get('g2bPblancNo') or combined_no
                                    budget = det_data.get('budgetAmount') or budget
                            except: pass
                            progrs = it.get('progrsSttus') or "진행중"
                            if ("진행중" in progrs or progrs == "") and any(t in area for t in MUST_PASS_AREAS):
                                final_list.append({'출처': f"2.국방부({config['type']})", '번호': combined_no, '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': area, '마감일': format_date_clean(clos_dt_full), 'URL': 'https://www.d2b.go.kr'})
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
                h_fmt = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#1F4E78', 'border': 1, 'align': 'center'})
                b_fmt = workbook.add_format({'border': 1, 'align': 'left'})
                n_fmt = workbook.add_format({'border': 1, 'align': 'right', 'num_format': '#,##0원'})
                for col_num, value in enumerate(df.columns.values): worksheet.write(0, col_num, value, h_fmt)
                worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
                for i, col in enumerate(df.columns):
                    width = 45 if col == '공고명' else 20
                    fmt = n_fmt if col == '예산' else b_fmt
                    worksheet.set_column(i, i, width, fmt)
            st.download_button(label="📥 통합 리포트(Excel) 다운로드", data=output.getvalue(), file_name=f"3사_통합_{today_str}.xlsx")
        else: status_st.warning("⚠️ 최근 조건에 맞는 공고가 없습니다.")
    except Exception as e: st.error(f"🚨 시스템 오류: {e}")
