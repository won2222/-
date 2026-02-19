import streamlit as st
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import io
import re
import pytz

# --- [1] 기본 설정 ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

def lh_korean_cleaner(text):
    if not text: return ""
    text = re.sub(r'<!\[CDATA\[|\]\]>', '', text)
    return text.strip()

# --- [2] UI 구성 ---
st.set_page_config(page_title="THE RADAR", layout="wide")
st.title("📡 THE RADAR v450.0")
st.subheader("LH & 국방부 정밀 기간 타격 시스템")

# --- [사이드바: 부장님 전용 컨트롤러] ---
st.sidebar.header("🛠️ 수색 엔진 설정")

# 1. 날짜 설정
st.sidebar.subheader("📅 수색 기간 설정")
col_s, col_e = st.sidebar.columns(2)
with col_s:
    s_date = st.sidebar.date_input("수색 시작일", datetime.now() - timedelta(days=7))
with col_e:
    e_date = st.sidebar.date_input("수색 종료일", datetime.now() + timedelta(days=7))

# 2. 키워드 설정
st.sidebar.subheader("🔑 필터 키워드")
default_kw = "폐기물, 운반, 폐목재, 임목, 나무, 벌채, 뿌리, 재활용, 잔재물, 가연성"
user_kw = st.sidebar.text_area("쉼표(,)로 구분하여 입력", default_kw, height=100)
kw_list = [k.strip() for k in user_kw.split(",") if k.strip()]

# 3. 지역 필터 (경기 최적화)
MUST_PASS_AREAS = ['경기', '평택', '화성', '서울', '인천', '전국', '제한없음']

if st.sidebar.button("🚀 전 구역 정밀 수색 개시", type="primary"):
    final_list = []
    s_str = s_date.strftime("%Y%m%d")
    e_str = e_date.strftime("%Y%m%d")
    
    status_st = st.empty()
    prog = st.progress(0)
    
    try:
        # --- 1. LH (성공한 정밀 로직) ---
        status_st.info("📡 [1/3] LH 공사 파트 정밀 수색 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            p_lh = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'tndrbidRegDtStart': s_str, 'tndrbidRegDtEnd': e_str, 'cstrtnJobGb': '1'}
            res_lh = requests.get(url_lh, params=p_lh, headers=HEADERS, timeout=20)
            res_lh.encoding = res_lh.apparent_encoding
            clean_xml = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
            
            if "<resultCode>00</resultCode>" in clean_xml:
                root = ET.fromstring(f"<root>{clean_xml}</root>")
                for item in root.findall('.//item'):
                    bid_nm = lh_korean_cleaner(item.findtext('bidnmKor'))
                    if any(kw in bid_nm for kw in kw_list):
                        final_list.append({
                            '출처': 'LH', '번호': item.findtext('bidNum'), '공고명': bid_nm,
                            '수요기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt') or 0, errors='coerce')),
                            '지역': '전국', '마감일': format_date_clean(item.findtext('openDtm')),
                            'URL': f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                        })
        except Exception as e: st.sidebar.error(f"LH 오류: {e}")
        prog.progress(33)

        # --- 2. 국방부 (D2B - 부장님 요청 기간 연동) ---
        status_st.info("📡 [2/3] 국방부(D2B) 기간 필터 수색 중...")
        d2b_configs = [
            {'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'c': 'biddocPresentnClosDt'}, 
            {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'c': 'prqudoPresentnClosDt'}
        ]
        for cfg in d2b_configs:
            try:
                # 국방부는 마감일 기준으로 검색 (부장님이 설정한 시작~종료일 범위 내 마감 건)
                p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
                if cfg['t'] == '일반':
                    # 일반공고는 등록일/마감일 검색 파라미터가 API마다 다르므로 전체 로드 후 필터링
                    pass 
                else:
                    p_d.update({'prqudoPresentnClosDateBegin': s_str, 'prqudoPresentnClosDateEnd': e_str})
                
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for it in ([items_d] if isinstance(items_d, dict) else items_d):
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = str(it.get(cfg['c'], ''))[:8]
                    
                    if any(kw in bid_nm for kw in kw_list):
                        # 부장님이 설정한 날짜 범위 내에 있는지 확인
                        if s_str <= clos_dt <= e_str:
                            area = it.get('areaLmttList') or "국방부"
                            if any(ok in area for ok in MUST_PASS_AREAS):
                                final_list.append({
                                    '출처': f"D2B({cfg['t']})", '번호': it.get('pblancNo') or it.get('dcsNo'),
                                    '공고명': bid_nm, '수요기관': it.get('ornt'),
                                    '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or it.get('budgetAmount') or 0, errors='coerce')),
                                    '지역': area, '마감일': format_date_clean(it.get(cfg['c'])),
                                    'URL': 'https://www.d2b.go.kr'
                                })
            except: continue
        prog.progress(66)

        # --- 3. 나라장터 (G2B) ---
        status_st.info("📡 [3/3] 나라장터 수색 중...")
        # ... (나라장터 로직 생략 없이 수행)
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        for kw in kw_list[:5]: # 상위 5개 키워드 위주 속도전
            try:
                p_g = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_str+'0000', 'inqryEndDt': e_str+'2359', 'bidNtceNm': kw}
                res_g = requests.get(url_g2b, params=p_g).json()
                items_g = res_g.get('response', {}).get('body', {}).get('items', [])
                for it in ([items_g] if isinstance(items_g, dict) else items_g):
                    final_list.append({
                        '출처': 'G2B', '번호': it.get('bidNtceNo'), '공고명': it.get('bidNtceNm'),
                        '수요기관': it.get('dminsttNm'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or 0, errors='coerce')),
                        '지역': '전국(공고참조)', '마감일': format_date_clean(it.get('bidClseDt')),
                        'URL': it.get('bidNtceDtlUrl')
                    })
            except: continue
        prog.progress(100)

        # --- [결과 출력] ---
        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 수색 완료! 총 {len(df)}건의 타겟을 포착했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='RADAR')
            st.download_button(label="📥 통합 리포트 다운로드", data=output.getvalue(), file_name=f"RADAR_{s_str}_{e_str}.xlsx")
        else:
            st.warning("⚠️ 해당 기간 및 키워드에 포착된 공고가 없습니다.")

    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
