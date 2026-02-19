import streamlit as st
import requests
import pandas as pd
import time
from urllib.parse import unquote, quote

# --- [1] 나라장터 직통 열쇠 재설정 ---
# 키가 이미 인코딩된 상태일 수 있으므로, 다시 풀었다가 requests가 알아서 처리하게 둡니다.
RAW_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
DECODED_KEY = unquote(RAW_KEY)

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", "부유", "잔재물", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기', '평택', '화성', '전국', '제한없음']

st.set_page_config(page_title="G2B RECOVERY", layout="wide")
st.title("📡 나라장터 엔진 정밀 복구모드")

if st.button("🚀 나라장터 직통 수색 개시"):
    final_list = []
    # 날짜 설정 (최근 7일)
    s_date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
    e_date = datetime.now().strftime("%Y%m%d")
    
    status = st.empty()
    
    for kw in KEYWORDS:
        status.info(f"🔎 현재 키워드 수색 중: {kw}")
        try:
            # 🎯 해결책: params에 넣지 않고 URL에 직접 쿼리 스트링을 구성 (인코딩 방지)
            url = f"http://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch"
            params = {
                'serviceKey': DECODED_KEY,
                'numOfRows': '100',
                'type': 'json',
                'inqryDiv': '1', # 1: 공고게시일 기준
                'inqryBgnDt': s_date + '0000',
                'inqryEndDt': e_date + '2359',
                'bidNtceNm': kw
            }
            
            # 🎯 해결책 2: 0.2초 대기 (서버 차단 방지)
            time.sleep(0.2)
            res = requests.get(url, params=params, timeout=10)
            
            if res.status_code == 200:
                data = res.json()
                items = data.get('response', {}).get('body', {}).get('items', [])
                if not items: continue
                
                for it in ([items] if isinstance(items, dict) else items):
                    # 면허/지역 2차 필터링 생략하고 우선 수집되는지 확인
                    final_list.append({
                        '출처': 'G2B_TEST',
                        '번호': it.get('bidNtceNo'),
                        '공고명': it.get('bidNtceNm'),
                        '기관': it.get('dminsttNm'),
                        '예산': it.get('asignBdgtAmt'),
                        '마감일': it.get('bidClseDt')
                    })
        except Exception as e:
            st.warning(f"⚠️ {kw} 수색 중 오류: {e}")

    if final_list:
        df = pd.DataFrame(final_list).drop_duplicates(subset=['번호'])
        st.success(f"✅ 나라장터 수색 성공! {len(df)}건을 찾았습니다.")
        st.dataframe(df)
    else:
        st.error("🚨 여전히 결과가 0건입니다. 서비스 키 권한 또는 서버 상태를 점검해야 합니다.")
