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



KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]

KWATER_KEYWORDS = ["부유물", "식물성", "초본류", "폐목재"]

KOGAS_KEYWORDS = ["폐목재", "가연성", "임목"]



OUR_LICENSES = ['1226', '1227', '6786', '6770']

MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']



KWATER_DETAIL_BASE = "https://ebid.kwater.or.kr/wq/index.do?w2xPath=/ui/index.xml&view=/bidpblanc/bidpblancsttus/BIDBD32000002.xml&tndrPbanno="

KOGAS_HOME = "https://k-ebid.kogas.or.kr"



def format_date_clean(val):

    if not val or val == "-": return "-"

    s = re.sub(r'[^0-9]', '', str(val))

    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"

    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"

    return val



# --- [2] 대시보드 레이아웃 ---

st.set_page_config(page_title="THE RADAR", layout="wide")

st.title("📡 THE RADAR")

st.caption("FRENERGY STRATEGIC PROCUREMENT INTELLIGENCE SYSTEM")

st.divider()



if st.sidebar.button("🔍 전략 수색 개시", type="primary"):

    final_list = []

    KST = pytz.timezone('Asia/Seoul')

    now = datetime.now(KST)

    

    s_date = (now - timedelta(days=4)).strftime("%Y%m%d")

    today_str = now.strftime("%Y%m%d")

    search_month = now.strftime('%Y%m') 

    last_month = (now - timedelta(days=28)).strftime('%Y%m') # 수자원용 지난달

    kogas_start = (now - timedelta(days=14)).strftime("%Y%m%d") 

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



        # --- 2. LH (성공 로직 유지) ---

        status_st.info("📡 [PHASE 2] LH 수색 중...")

        try:

            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"

            res_lh = requests.get(url_lh, params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}, headers=HEADERS, timeout=15)

            res_lh.encoding = res_lh.apparent_encoding

            clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()

            root = ET.fromstring(f"<root>{clean_xml}</root>")

            for item in root.findall('.//item'):

                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()

                if any(kw in bid_nm for kw in KEYWORDS):

                    b_no = item.findtext('bidNum')

                    final_list.append({'출처':'LH', '번호':b_no, '공고명':bid_nm, '수요기관':'LH', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce') or 0), '지역':'전국', '마감일':format_date_clean(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"})

        except: pass



        # --- 3. 국방부 ---

        status_st.info("📡 [PHASE 3] D2B 수색 중...")

        # ... (생략 - 기존 로직 유지) ...



        # --- 4. 수자원공사 (v181.0 + 수색 범위 확장) ---

        status_st.info("📡 [PHASE 4] K-water 수색 중 (1월~2월 통합)...")

        for m_kw in [last_month, search_month]:

            for kw in KWATER_KEYWORDS:

                try:

                    res_k = requests.get("http://apis.data.go.kr/B500001/ebid/tndr3/servcList", 

                                       params={'serviceKey': SERVICE_KEY, 'searchDt': m_kw, 'bidNm': kw, 'numOfRows': '500', '_type': 'json'}, 

                                       timeout=10).json()

                    k_items = res_k.get('response', {}).get('body', {}).get('items', {}).get('item', [])

                    k_items = [k_items] if isinstance(k_items, dict) else k_items

                    for kit in k_items:

                        title, raw_no = kit.get('tndrPblancNm', '-'), kit.get('tndrPbanno', '-')

                        if any(k in title for k in KWATER_KEYWORDS):

                            final_list.append({'출처': 'K-water', '번호': raw_no, '공고명': title, '수요기관': '수자원공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(kit.get('tndrPblancEnddt')), 'URL': f"{KWATER_DETAIL_BASE}{raw_no}"})

                except: continue
        # --- 5. 가스공사 (KOGAS) ---
        status_st.info("📡 [PHASE 5] KOGAS 수색 중...")
        try:
            res_kg = requests.get("http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'DOCDATE_START': kogas_start}, timeout=15)
            root_kg = ET.fromstring(res_kg.text)
            for item in root_kg.findall('.//item'):
                title = item.findtext('NOTICE_NAME') or '-'
                if any(kw in title for kw in KOGAS_KEYWORDS):
                    final_list.append({'출처': 'KOGAS', '번호': item.findtext('NOTICE_CODE') or '-', '공고명': title, '수요기관': '가스공사', '예산': 0, '지역': '전국', '마감일': format_date_clean(item.findtext('END_DT')), 'URL': KOGAS_DIRECT_URL})
        except: pass

        # --- [최종 출력] ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.metric("오늘의 전략 공고", f"{len(df)}건")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='RADAR_REPORT')
                workbook, worksheet = writer.book, writer.sheets['RADAR_REPORT']
                h_fmt = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#1E3A8A', 'border': 1, 'align': 'center'})
                for c_idx, val in enumerate(df.columns.values): worksheet.write(0, c_idx, val, h_fmt)
            st.download_button(label="📥 전략 리포트(Excel) 다운로드", data=output.getvalue(), file_name=f"RADAR_{today_str}.xlsx")
        else:
            st.warning("⚠️ 현재 조건에 부합하는 공고가 없습니다.")
    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")

