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
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

def format_date_clean(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val))
    if len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return val

# --- [2] 대시보드 레이아웃 ---
st.set_page_config(page_title="THE RADAR v3400", layout="wide")
st.title("📡 THE RADAR v3400.0")
st.error("🚀 국방부(D2B) 서버 강제 돌파 모드 가동 (응답 대기시간 30초 확장)")

if st.sidebar.button("🔍 국방부 포함 전 채널 재수색", type="primary"):
    final_list = []
    KST = pytz.timezone('Asia/Seoul')
    now = datetime.now(KST)
    
    # 날짜 규격 (기관별 맞춤)
    s_date = (now - timedelta(days=10)).strftime("%Y%m%d")
    today_str = now.strftime("%Y%m%d")
    target_end_day = (now + timedelta(days=10)).strftime("%Y%m%d")
    
    status_st = st.empty()
    log_st = st.expander("🛠️ 수집 실시간 현황", expanded=True)

    try:
        # --- 1. 나라장터 (성공 로직 유지) ---
        status_st.info("📡 [1/3] 나라장터 수색 중...")
        for kw in KEYWORDS:
            try:
                time.sleep(0.1)
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 
                     'inqryBgnDt': s_date+'0000', 'inqryEndDt': today_str+'2359', 'bidNtceNm': kw}
                res = requests.get('https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch', params=p, timeout=10).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                for it in ([items] if isinstance(items, dict) else items):
                    final_list.append({'출처':'G2B', '번호':it.get('bidNtceNo'), '공고명':it.get('bidNtceNm'), '수요기관':it.get('dminsttNm'), '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0))), '지역':'공고참조', '마감일':format_date_clean(it.get('bidClseDt')), 'URL':it.get('bidNtceDtlUrl')})
            except: continue
        log_st.write("✅ 나라장터 수색 완료")

        # --- 2. LH (성공 로직 유지) ---
        status_st.info("📡 [2/3] LH포털 수색 중...")
        try:
            res_lh = requests.get("http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev", params={'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 'tndrbidRegDtStart': s_date, 'tndrbidRegDtEnd': today_str, 'cstrtnJobGb': '1'}, timeout=20)
            root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text).strip())
            for item in root.findall('.//item'):
                bid_nm = item.findtext('bidnmKor', '')
                if any(kw in bid_nm for kw in KEYWORDS):
                    final_list.append({'출처':'LH', '번호':item.findtext('bidNum'), '공고명':bid_nm, '수요기관':'LH공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt') or 0)), '지역':'전국', '마감일':format_date_clean(item.findtext('openDtm')), 'URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={item.findtext('bidNum')}"})
        except: pass
        log_st.write("✅ LH 수색 완료")

        # --- 3. 국방부 (강제 돌파 로직) ---
        status_st.info("📡 [3/3] 국방부(D2B) 강제 돌파 시도 중...")
        d2b_configs = [
            {'t': '일반', 'l': 'getDmstcCmpetBidPblancList', 'd': 'getDmstcCmpetBidPblancDetail'}, 
            {'t': '수의', 'l': 'getDmstcOthbcVltrnNtatPlanList', 'd': 'getDmstcOthbcVltrnNtatPlanDetail'}
        ]
        
        for cfg in d2b_configs:
            try:
                # 🎯 핵심: 국방부 전용 타임아웃 30초 및 재시도
                p_d = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', '_type': 'json'}
                if cfg['t'] == '수의':
                    p_d.update({'prqudoPresentnClosDateBegin': s_date, 'prqudoPresentnClosDateEnd': target_end_day})
                
                # 국방부 서버는 응답이 매우 느리므로 timeout을 30초로 설정
                res_d = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['l']}", params=p_d, timeout=30).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                
                for it in ([items_d] if isinstance(items_d, dict) else items_d):
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    if any(kw in bid_nm for kw in KEYWORDS):
                        # 🎯 상세 조회를 통해 SCU번호(g2bPblancNo) 강제 추출
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': str(it.get('pblancOdr', '1')).split('.')[0], 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if cfg['t'] == '수의': p_det.update({'ntatPlanDate': it.get('ntatPlanDate'), 'iemNo': it.get('iemNo')})
                        
                        try:
                            det = requests.get(f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{cfg['d']}", params=p_det, timeout=20).json().get('response', {}).get('body', {}).get('item', {})
                            area = det.get('areaLmttList') or "상세참조"
                            if any(t in area for t in MUST_PASS_AREAS):
                                final_list.append({
                                    '출처': f"D2B({cfg['t']})", 
                                    '번호': det.get('g2bPblancNo') or it.get('pblancNo'), 
                                    '공고명': bid_nm, '수요기관': it.get('ornt'), 
                                    '예산': int(pd.to_numeric(det.get('budgetAmount') or it.get('asignBdgtAmt') or 0)), 
                                    '지역': area, 
                                    '마감일': format_date_clean(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')), 
                                    'URL': 'https://www.d2b.go.kr'
                                })
                                log_st.write(f"✅ 국방부 확보: {bid_nm[:20]}...")
                        except:
                            # 상세조회 실패시 목록 데이터라도 수집
                            final_list.append({'출처': f"D2B({cfg['t']})", '번호': it.get('pblancNo'), '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': 0, '지역': '상세참조', '마감일': format_date_clean(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')), 'URL': 'https://www.d2b.go.kr'})
            except Exception as e:
                log_st.error(f"❌ 국방부 {cfg['t']} 엔진 재시도 필요: {e}")

        # --- [결과 처리] ---
        status_st.empty()
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['번호']).sort_values(by=['마감일'])
            st.success(f"✅ 최종 승인! {len(df)}건 확보 (국방부 통합 완료)")
            st.dataframe(df.style.format({'예산': '{:,}원'}), use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button(label="📥 통합 전략 리포트 저장", data=output.getvalue(), file_name=f"RADAR_FINAL_v3400.xlsx")
        else:
            st.error("🚨 수색 실패. 키워드 매칭은 되나 필터링 과정에서 모두 걸러졌을 수 있습니다.")

    except Exception as e:
        st.error(f"🚨 시스템 오류: {e}")
