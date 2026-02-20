import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import io
import re

# --- [1] 부장님 정예 키워드 및 설정 ---
SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "가연성", "임목", "잔재물"]
# 🎯 국방부 관련 기관 코드 및 명칭
MILITARY_ORGS = ["국방부", "육군", "해군", "공군", "국군", "해병대", "방위사업청"]

st.set_page_config(page_title="THE RADAR v4700", layout="wide")
st.title("📡 THE RADAR v4700.0")
st.info("🚀 국방부 서버 불통에 따른 '나라장터 우회 수색' 모드 가동")

if st.sidebar.button("🔍 나라장터 기반 국방부 물량 수색", type="primary"):
    final_list = []
    now = datetime.now()
    s_date = (now - timedelta(days=15)).strftime("%Y%m%d") + "0000"
    e_date = now.strftime("%Y%m%d") + "2359"
    
    status_st = st.empty()
    
    try:
        # 🎯 국방부(D2B) 대신 나라장터(G2B) 서버에 접속
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch'
        
        for kw in KEYWORDS:
            status_st.info(f"📡 나라장터 내 국방부 '{kw}' 물량 추적 중...")
            params = {
                'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json',
                'inqryDiv': '1', 'inqryBgnDt': s_date, 'inqryEndDt': e_date, 'bidNtceNm': kw
            }
            
            res = requests.get(url_g2b, params=params, timeout=15).json()
            items = res.get('response', {}).get('body', {}).get('items', [])
            items = [items] if isinstance(items, dict) else items
            
            for it in items:
                org_nm = it.get('dminsttNm', '')
                # 🎯 나라장터 전체 데이터 중 수요기관이 '군' 관련인 것만 필터링
                if any(m in org_nm for m in MILITARY_ORGS):
                    final_list.append({
                        '출처': 'G2B(국방물량)',
                        '공고번호': it.get('bidNtceNo'),
                        '공고명': it.get('bidNtceNm'),
                        '수요기관': org_nm,
                        '예산': int(pd.to_numeric(it.get('asignBdgtAmt', 0))),
                        '마감일': it.get('bidClseDt')[:10] if it.get('bidClseDt') else "-",
                        'URL': it.get('bidNtceDtlUrl')
                    })

        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['공고번호'])
            st.success(f"✅ 나라장터 우회 수색으로 총 {len(df)}건의 국방 물량을 확보했습니다!")
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("🚨 나라장터에도 현재 국방부 관련 키워드 공고가 없습니다.")

    except Exception as e:
        st.error(f"🚨 우회 수색 중 오류: {e}")
