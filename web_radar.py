import requests
import pandas as pd
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from datetime import datetime, timedelta
import sys
import re
import traceback
from concurrent.futures import ThreadPoolExecutor # 속도 해결사

# --- [1] 부장님 커스텀 세팅 (로직 보존) ---
SERVICE_KEY = unquote('9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0')
HEADERS = {'User-Agent': 'Mozilla/5.0'}
KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽", "식물성", "부유물", "초본류", "초목류"]
OUR_LICENSES = ['1226', '1227', '6786', '6770']
MUST_PASS_AREAS = ['경기도', '평택', '화성', '서울', '인천', '전국', '제한없음']

# --- [2] 유틸리티 함수 (로직 보존) ---
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

def print_progress(current, total, prefix='', keyword='', length=30):
    percent = f"{100 * (current / float(total)):.1f}"
    filled_length = int(length * current // total)
    bar = '█' * filled_length + '-' * (length - filled_length)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% ({current}/{total}) [작업중: {keyword}]')
    sys.stdout.flush()

# --- [3] 초고속 상세정보 수집기 (멀티스레드용) ---
def fetch_g2b_detail(it):
    try:
        b_no, b_ord = it['bidNtceNo'], str(it.get('bidNtceOrd', '0')).zfill(2)
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        # 면허
        l_res = requests.get(url_g2b + 'getBidPblancListInfoLicenseLimit', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=3).json()
        lic_val = " / ".join(list(set([li.get('lcnsLmtNm','') for li in l_res.get('response',{}).get('body',{}).get('items',[]) if li.get('lcnsLmtNm')]))) or "공고참조"
        # 지역
        r_res = requests.get(url_g2b + 'getBidPblancListInfoPrtcptPsblRgn', params={'serviceKey': SERVICE_KEY, 'type': 'json', 'inqryDiv': '2', 'bidNtceNo': b_no, 'bidNtceOrd': b_ord}, timeout=3).json()
        reg_val = ", ".join(list(set([ri.get('prtcptPsblRgnNm','') for ri in r_res.get('response',{}).get('body',{}).get('items',[]) if ri.get('prtcptPsblRgnNm')]))) or "전국"
        
        if (any(code in lic_val for code in OUR_LICENSES) or lic_val == "공고참조") and any(ok in reg_val for ok in MUST_PASS_AREAS):
            return {'출처':'나라장터', '공고번호':b_no, '공고명':it['bidNtceNm'], '수요기관':it['dminsttNm'], '예산':int(pd.to_numeric(it.get('asignBdgtAmt', 0), errors='coerce') or 0), '지역(제한)':reg_val, '면허정보':lic_val, '마감일시':format_date_clean(it.get('bidClseDt')), '상세URL':it.get('bidNtceDtlUrl')}
    except: pass
    return None

def run_v254_turbo_radar():
    try:
        final_list = []
        now = datetime.now()
        s_date_api = (now - timedelta(days=5)).strftime("%Y%m%d")
        today_api = now.strftime("%Y%m%d")
        d2b_start, d2b_end = today_api, (now + timedelta(days=3)).strftime("%Y%m%d")

        print(f"\n🚀 [v254.0] 전국 3사 통합 레이더 (초고속 터보 모드)")
        print(f"{'='*85}")
        print(f"📡 검색 기간: {format_date_clean(s_date_api)} ~ {format_date_clean(today_api)} (국방부 마감 ~{d2b_end})")
        print(f"{'='*85}\n")

        # --- 1. 나라장터 (G2B) - 멀티스레드 적용 ---
        print(f"📡 [1단계] 나라장터 초고속 분석 중...")
        url_g2b = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'
        for kw in KEYWORDS:
            try:
                p = {'serviceKey': SERVICE_KEY, 'numOfRows': '100', 'type': 'json', 'inqryDiv': '1', 'inqryBgnDt': s_date_api+'0000', 'inqryEndDt': today_api+'2359', 'bidNtceNm': kw}
                res = requests.get(url_g2b + 'getBidPblancListInfoServcPPSSrch', params=p, timeout=5).json()
                items = res.get('response', {}).get('body', {}).get('items', [])
                items = [items] if isinstance(items, dict) else items
                
                # 병렬 처리로 속도 대폭 향상
                with ThreadPoolExecutor(max_workers=10) as executor:
                    results = list(executor.map(fetch_g2b_detail, items))
                    final_list.extend([r for r in results if r])
                print_progress(KEYWORDS.index(kw)+1, len(KEYWORDS), prefix='    🔎 G2B 키워드', keyword=kw)
            except: pass

        # --- 2. LH (e-Bid) ---
        print(f"\n\n📡 [2단계] LH포털 수집 중...")
        try:
            url_lh = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
            res_lh = requests.get(url_lh, params={'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'pageNo': '1', 'tndrbidRegDtStart': s_date_api, 'tndrbidRegDtEnd': today_api}, timeout=10)
            res_lh.encoding = res_lh.apparent_encoding
            root = ET.fromstring(re.sub(r'<\?xml.*\?>', '', res_lh.text))
            lh_items = root.findall('.//item')
            for i, item in enumerate(lh_items):
                bid_nm = re.sub(r'<!\[CDATA\[|\]\]>', '', item.findtext('bidnmKor', '')).strip()
                if any(kw in bid_nm for kw in KEYWORDS):
                    b_no = item.findtext('bidNum')
                    final_list.append({'출처':'LH', '공고번호':b_no, '공고명':bid_nm, '수요기관':'한국토지주택공사', '예산':int(pd.to_numeric(item.findtext('fdmtlAmt'), errors='coerce') or 0), '지역(제한)':'전국/상세참조', '면허정보':'LH전수수집', '마감일시':format_date_clean(item.findtext('openDtm')), '상세URL':f"https://ebid.lh.or.kr/ebid.et.tp.cmd.BidsrvcsDetailListCmd.dev?bidNum={b_no}&bidDegree=00"})
                print_progress(i+1, len(lh_items), prefix='    🔍 LH 데이터분석', keyword='LH 전수조사')
        except: pass

        # --- 3. 국방부 (D2B) - 병렬 처리 적용 ---
        print(f"\n\n📡 [3단계] 국방부 초고속 수색 중 (v140.0 로직)...")
        for op in ['getDmstcCmpetBidPblancList', 'getDmstcOthbcVltrnNtatPlanList']:
            try:
                url_d = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{op}"
                res_d = requests.get(url_d, params={'serviceKey': SERVICE_KEY, 'numOfRows': '400', '_type': 'json'}, headers=HEADERS, timeout=10).json()
                items_d = res_d.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                items_d = [items_d] if isinstance(items_d, dict) else items_d
                
                def fetch_d2b_detail(it):
                    try:
                        bid_nm = it.get('bidNm') or it.get('othbcNtatNm', '')
                        clos_dt = get_safe_date(it.get('biddocPresentnClosDt') or it.get('prqudoPresentnClosDt'))
                        if (op == 'getDmstcCmpetBidPblancList' and d2b_start <= clos_dt <= d2b_end and any(kw in bid_nm for kw in KEYWORDS)) or \
                           (op == 'getDmstcOthbcVltrnNtatPlanList' and any(kw in bid_nm for kw in KEYWORDS)):
                            det_op = op.replace('List', 'Detail')
                            url_det = f"http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/{det_op}"
                            p_det = {'serviceKey': SERVICE_KEY, 'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'), 'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'), 'dcsNo': it.get('dcsNo'), '_type': 'json'}
                            if 'Othbc' in op: p_det.update({'iemNo': it.get('iemNo'), 'ntatPlanDate': it.get('ntatPlanDate')})
                            det = requests.get(url_det, params=p_det, headers=HEADERS, timeout=5).json().get('response', {}).get('body', {}).get('item', {})
                            return {'출처':'국방부', '공고번호':it.get('pblancNo') or it.get('dcsNo'), '공고명':bid_nm, '수요기관':it.get('ornt'), '예산':int(pd.to_numeric(det.get('budgetAmount') or it.get('asignBdgtAmt') or 0, errors='coerce') or 0), '지역(제한)':det.get('areaLmttList') or "제한없음", '면허정보':det_op, '마감일시':format_date_clean(clos_dt), '상세URL':'https://www.d2b.go.kr'}
                    except: pass
                    return None

                with ThreadPoolExecutor(max_workers=10) as executor:
                    results = list(executor.map(fetch_d2b_detail, items_d))
                    final_list.extend([r for r in results if r])
                print_progress(1, 1, prefix='    🛡️ 국방부 분석완료', keyword=op)
            except: pass

        # --- 4. 저장 ---
        if final_list:
            print(f"\n\n📊 [4단계] 리포트 생성 중...")
            df = pd.DataFrame(final_list).drop_duplicates(subset=['출처', '공고번호']).sort_values(by=['출처', '마감일시'])
            file_name = f"3사_통합_리포트_터보.xlsx"
            writer = pd.ExcelWriter(file_name, engine='xlsxwriter')
            df.to_excel(writer, index=False, sheet_name='통합공고')
            workbook, worksheet = writer.book, writer.sheets['통합공고']
            h_fmt = workbook.add_format({'bold':True, 'font_color':'white', 'bg_color':'#1F4E78', 'border':1, 'align':'center', 'valign':'vcenter'})
            n_fmt = workbook.add_format({'num_format':'#,##0원', 'border':1, 'align':'right', 'valign':'vcenter'})
            c_fmt = workbook.add_format({'border':1, 'align':'left', 'valign':'vcenter', 'text_wrap': True})
            m_fmt = workbook.add_format({'border':1, 'align':'center', 'valign':'vcenter'})
            worksheet.set_default_row(25)
            widths = [10, 15, 55, 25, 18, 25, 30, 18, 60]
            for i, width in enumerate(widths):
                options = {'hidden': True} if i == 6 else {}
                worksheet.write(0, i, df.columns[i], h_fmt)
                if i == 4: worksheet.set_column(i, i, width, n_fmt, options)
                elif i in [0, 1, 7]: worksheet.set_column(i, i, width, m_fmt, options)
                else: worksheet.set_column(i, i, width, c_fmt, options)
            writer.close()
            print(f"\n{'='*85}\n✅ 작전 성공! 총 {len(df)}건을 초고속으로 확보했습니다. 파일: {file_name}\n{'='*85}")
        else: print("\n⚠️ 검색 결과가 없습니다.")
    except: traceback.print_exc()
    finally: input("\n☕ 작업 종료. 엔터를 누르면 종료됩니다...")

if __name__ == "__main__":
    run_v254_turbo_radar()