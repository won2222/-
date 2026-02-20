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

# --- [1] 부장님 정예 설정 (v161 완벽 복원) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류", "임목", "폐가구", "대형", "적환장"]
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v3300", layout="wide")
st.title("📡 THE RADAR v3300.0")
st.error("🚀 [긴급] 데이터 수집 강제 활성화 모드 (누락 방지 엔진 장착)")

if st.sidebar.button("🔍 데이터 강제 수집 개시", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 🎯 [날짜 규격 강제 동기화]
    s_date = (now - timedelta(days=10)).strftime("%Y%m%d") # 7일에서 10일로 확장
    today_str = now.strftime("%Y%m%d")
    
    status_st = st.empty()
    log_st = st.expander("🛠️ 실시간 수집 로그 (에러 추적용)", expanded=True)

    try:
        # --- 1. 나라장터 (가장 예민한 녀석) ---
        status_st.info("📡 [1/3] 나라장터 침투 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        
        for kw in KEYWORDS:
            try:
                time.sleep(0.3) # 🎯 서버 차단 방지용 딜레이 강화
                params = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 
                          'inqryBgnDt': s_date+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b, params=params, timeout=15)
                
                if res.status_code == 200:
                    data = res.json()
                    items = data.get('response', {}).get('body', {}).get('items', [])
                    if not items:
                        log_st.write(f"⚠️ {kw}: 검색 결과 없음")
                        continue
                        
                    for it in ([items] if isinstance(items, dict) else items):
                        b_no = it.get('bidNtceNo')
                        # 🎯 상세 검증 생략하고 우선 수집 (나중에 필터링)
                        final_list.append({
                            '출처':'G2B', '번호':b_no, '공고명':it.get('bidNtceNm'), 
                            '수요기관':it.get('dminsttNm'), '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0))),
                            '지역':'G2B공고', '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')
                        })
                        log_st.write(f"✅ {kw}: {it.get('bidNtceNm')[:20]}... 확보")
            except Exception as e:
                log_st.error(f"❌ {kw} 수색 중 에러: {e}")

        # --- 2. LH (XML 고집쟁이) ---
        status_st.info("📡 [2/3] LH포털 침투 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            res_lh = requests.get(url_lh, params={'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}, timeout=20)
            lh_raw = re.sub(r'<\?xml.*\?>', '', res_lh.text).strip()
            root = ET.fromstring(f"<root>{lh_raw}</root>")
            for item in root.findall('.//item'):
                bid_nm = item.findtext('bidnmKor', '')
                if any(kw in bid_nm for kw in KEYWORDS):
                    final_list.append({
                        '출처':'LH', '번호':item.findtext('bidNum'), '공고명':bid_nm, 
                        '수요기관':'한국토지주택공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)),
                        '지역':'전국', '마감일':format_date_clean(item.findtext('openDtm')), 
                        'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"
                    })
                    log_st.write(f"✅ LH: {bid_nm[:20]}... 확보")
        except Exception as e:
            log_st.error(f"❌ LH 수색 실패: {e}")

        # --- 3. 국방부 (부장님 v161 SCU 엔진) ---
        status_st.info("📡 [3/3] 국방부 정밀 추적 중...")
        d2b_configs = [{'t': '일반', 'l': 'getDmstcCmpetBidPblancList'}, {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList'}]
        for cfg in d2b_configs:
            try:
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}, timeout=20).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                for it in ([items_d] if isinstance(items_d, dict) else items_d):
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in KEYWORDS):
                        final_list.append({
                            '출처': f"D2B({cfg['t']})", '번호': it.get('pblancNo') or it.get('dcsNo'), 
                            '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(it.get('asignBdgtAmt') or 0)),
                            '지역': '상세참조', '마감일': format_date_clean(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')), 
                            'URL': 'https://www.d2b.go.kr'
                        })
                        log_st.write(f"✅ 국방부({cfg['t']}): {bid_nm[:20]}... 확보")
            except Exception as e:
                log_st.error(f"❌ 국방부 {cfg['t']} 수색 실패: {e}")

        # --- [결과 처리] ---
        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 작전 성공! 총 {len(df)}건을 확보했습니다.")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 수집 데이터 저장", data=output.getvalue(), file_name=f"RADAR_DEBUG_{today_str}.xlsx")
        else:
            st.error("🚨 전 기관 데이터 응답 없음. 서비스 키의 일일 트래픽이 소진되었거나 서버 점검 중일 가능성이 매우 높습니다.")

    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
