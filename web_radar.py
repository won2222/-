import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import sys
import re
import time
import traceback

# --- 부장님 커스텀 세팅 (키워드 18종 확장) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "식물성", "낙엽", "임목", "가연성", 
            "부유", "잔재물", "반입불가", "초본류", "초목류", "폐가구", "대형", "적환장", "매립", "재활용"]
MUST_PASS = ['경기도', '평택시', '화성시', '서울특별시', '서울', '인천', '전국']
EXCLUDE_LIST = ['충청', '전라', '강원', '경상', '제주', '부산', '대구', '광주', '대전', '울산', '세종', '충북', '충남', '경북', '경남', '전북', '전남']

def clean_date_strict(val):
    if not val or val == "-": return "-"
    s = re.sub(r'[^0-9]', '', str(val).split('.')[0])
    try:
        if len(s) >= 12: return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
        elif len(s) >= 8: return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return val
    except: return val

# 📊 진도율 표시 함수
def print_progress(current, total, prefix='', length=30):
    percent = f"{100 * (current / float(total)):.1f}"
    filled_length = int(length * current // total)
    bar = '█' * filled_length + '-' * (length - filled_length)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% ({current}/{total})')
    sys.stdout.flush()

def run_v169_dashboard_radar():
    try:
        final_list = []
        now = datetime.now()
        
        # 날짜 계산 (대시보드 표기용)
        s_date_disp = (now - timedelta(days=4)).strftime("%Y.%m.%d")
        today_disp = now.strftime("%Y.%m.%d")
        e_date_disp = (now + timedelta(days=4)).strftime("%Y.%m.%d")
        
        # API 검색용 날짜
        s_date_api = (now - timedelta(days=4)).strftime("%Y%m%d")
        target_end_day = (now + timedelta(days=4)).strftime("%Y%m%d")

        # 🚨 [부장님 오더] 대시보드 출력
        print(f"\n{'='*70}")
        print(f"🚀 [v169.0] 전국 3사 통합 레이더 (작전 상황실)")
        print(f"{'='*70}")
        print(f"📡 나라장터 검색 기준 : 공고일 ({s_date_disp} ~ {today_disp})")
        print(f"📡 LH 검색 기준       : 공고일 ({s_date_disp} ~ {today_disp})")
        print(f"📡 방위사업청 검색 기준: 마감일 ({today_disp} ~ {e_date_disp})")
        print(f"📦 검색 키워드 (18종):")
        for i in range(0, len(KEYWORDS), 6):
            print(f"   {', '.join(KEYWORDS[i:i+6])}")
        print(f"{'='*70}\n")

        # --- 1. 나라장터 (G2B) ---
        print(f"📡 [1단계] 나라장터(G2B) 수색 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        g_raw = []
        for i, kw in enumerate(KEYWORDS):
            print_progress(i+1, len(KEYWORDS), prefix='   🔎 키워드 수집')
            params = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date_api+'0000', 'inqryEndDt': today_disp.replace('.','')+'2359', 'bidNtceNm': kw}
            try:
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=params, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                for it in ([items] if isinstance(items, dict) else items):
                    it['searchKeyword'] = kw
                    g_raw.append(it)
            except: pass
        
        if g_raw:
            df_g = pd.DataFrame(g_raw).drop_duplicates(subset=['bidNtceNo'])
            print(f"\n   ⚙️ G2B 상세 분석 (지역필터링)")
            for i, (idx, row) in enumerate(df_g.iterrows()):
                print_progress(i+1, len(df_g), prefix='   👉 데이터 검증')
                b_no, b_ord = row['bidNtceNo'], str(row.get('bidNtceOrd', '00')).zfill(2)
                reg_val, is_pass = "제한없음", True
                try:
                    r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'ServiceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=2).json()
                    regs = [str(ri.get('prtcptPsblRgnNm', '')) for ri in r_res.get('response', {}).get('body', {}).get('items', [])]
                    reg_val = ", ".join(list(set(regs))) if regs else "제한없음"
                    if not (any(ok in reg_val for ok in MUST_PASS) or reg_val == "제한없음"):
                        if any(no in reg_val for no in EXCLUDE_LIST): is_pass = False
                except: reg_val = "공고참조"

                if is_pass:
                    final_list.append({'출처': '1.나라장터', '키워드': row['searchKeyword'], '공고번호': b_no, '공고명': row['bidNtceNm'], '수요기관': row['dminsttNm'], '예산': int(pd.to_numeric(row.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역': reg_val, '면허(숨김)': '상세참조', '마감일시': clean_date_strict(row.get('bidClseDt')), '상세URL': row.get('bidNtceDtlUrl', '')})

        # --- 2. LH (e-Bid) ---
        print(f"\n\n📡 [2단계] LH포털 수색 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            res_lh = requests.get(url_lh, params={'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500', 'tndrbidRegDtStart': s_date_api, 'tndrbidRegDtEnd': today_disp.replace('.',''), 'cstrtnJobGb': '1'}, timeout=10)
            res_lh.encoding = res_lh.apparent_encoding
            root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text))
            lh_items = root.findall('.//item')
            for i, item in enumerate(lh_items):
                print_progress(i+1, len(lh_items), prefix='   🔍 LH 데이터 분석')
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    b_no = item.findtext('bidNum')
                    lh_url = f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"
                    final_list.append({'출처': '2.LH', '키워드': 'LH검색', '공고번호': b_no, '공고명': bid_nm, '수요기관': '한국토지주택공사', '예산': int(pd.to_numeric(item.findtext('fdmtlAmt'), errors='coerce') or 0), '지역': '전국/공고참조', '면허(숨김)': '상세참조', '마감일시': clean_date_strict(item.findtext('openDtm')), '상세URL': lh_url})
        except: pass

        # --- 3. 방위사업청 (D2B) - 예산 복구 정밀수집 ---
        print(f"\n\n📡 [3단계] 방위사업청(D2B) 예산 정밀 추적 중...")
        try:
            for bt in ['bid', 'priv']:
                url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancList' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanList'}"
                res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, headers=HEADERS, timeout=10).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                
                for i, it in enumerate(items_d):
                    print_progress(i+1, len(items_d), prefix=f'   🛡️ 국방부({bt}) 분석')
                    bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                    clos_dt = it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt')
                    if any(kw in bid_nm for kw in KEYWORDS) and (bt=='priv' or (today_disp.replace('.','') <= str(clos_dt)[:8] <= target_end_day)):
                        
                        # 🎯 [핵심] 국방부 예산 2차 정밀 파싱 로직
                        budget = it.get('asignBdgtAmt') or it.get('budgetAmount') or 0
                        url_det = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{'getDmstcCmpetBidPblancDetail' if bt=='bid' else 'getDmstcOthbcVltrnNtatPlanDetail'}"
                        p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'), 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                        if bt == 'priv': p_det.update({'iemNo': it.get('iemNo'), 'ntatPlanDate': it.get('ntatPlanDate')})
                        
                        try:
                            # 상세 페이지 API에서 정확한 예산(budgetAmount) 재추출
                            det_res = requests.get(url_det, params=p_det, timeout=5).json()
                            det_item = det_res.get('response', {}).get('body', {}).get('item', {})
                            budget = det_item.get('budgetAmount') or budget
                        except: pass

                        final_list.append({'출처': '3.국방부', '키워드': '국방검색', '공고번호': it.get('pblancNo') or it.get('dcsNo'), '공고명': bid_nm, '수요기관': it.get('ornt'), '예산': int(pd.to_numeric(budget, errors='coerce') or 0), '지역': '상세확인', '면허(숨김)': '상세확인', '마감일시': clean_date_strict(clos_dt), '상세URL': 'https://www.d2b.go.kr/pdb/bid/bidAnnounceView.do'})
        except: pass

        # --- 4. 최종 저장 ---
        if final_list:
            df = pd.DataFrame(final_list).drop_duplicates(subset=['공고번호']).sort_values(by=['출처', '마감일시'])
            file_name = f"전국_3사_통합리포트_v169_{now.strftime('%m%d_%H%M')}.xlsx"
            writer = pd.ExcelWriter(file_name, engine='xlsxwriter')
            df.to_excel(writer, index=False, sheet_name='통합공고')
            workbook, worksheet = writer.book, writer.sheets['통합공고']
            
            # 서식 (v160과 동일)
            h_fmt = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#1F4E78', 'border': 1, 'align': 'center'})
            n_fmt = workbook.add_format({'border': 1, 'num_format': '#,##0원', 'align': 'right'})
            c_fmt = workbook.add_format({'border': 1, 'align': 'left'})
            worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
            widths = [12, 10, 18, 50, 25, 18, 25, 15, 20, 60]
            for i, w in enumerate(widths):
                worksheet.write(0, i, df.columns[i], h_fmt)
                if i in [1, 7]: worksheet.set_column(i, i, 0, None, {'hidden': True})
                elif i == 5: worksheet.set_column(i, i, w, n_fmt)
                else: worksheet.set_column(i, i, w, c_fmt)
            writer.close()
            print(f"\n\n{'='*70}\n🎯 작전 성공! {len(df)}건 확보 완료! 파일: {file_name}\n{'='*70}")
        else: print("\n⚠️ 검색 결과가 없습니다.")

    except Exception: traceback.print_exc()
    finally: input("\n엔터를 누르면 종료됩니다.")

if __name__ == "__main__":
    run_v169_dashboard_radar()
