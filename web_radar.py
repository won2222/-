# -*- coding: utf-8 -*-
"""
통합 입찰공고 검색 (나라장터 / 국방부 / LH / 가스공사 / 수자원공사)
검색기간: 오늘 기준 7일 | 키워드·지역·면허 필터 통합

[테스트 모드]
  TEST_MODE = True  → 지역·면허 필터 OFF, 전체 결과 노출 (필터 확인용)
  TEST_MODE = False → 경기도/평택/화성/전국 + 면허코드 필터 ON (실운영)
"""

import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import unquote
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

# =====================================================================
# 0. 공통 설정
# =====================================================================
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

SERVICE_KEY = '9ada16f8e5bc00e68aa27ceaa5a0c2ae3d4a5e0ceefd9fdca653b03da27eebf0'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

TODAY      = datetime.now()
SEARCH_START = TODAY - timedelta(days=6)
SEARCH_END   = TODAY

KEYWORDS = ["폐기물", "운반", "폐목재", "폐합성수지", "잔재물", "가연성", "낙엽",
            "식물성", "부유물", "초본류", "초목류", "임목", "폐가구"]

# ── 면허 필터 ──
OUR_LICENSES       = ['1226', '1227', '6786', '6770']
WASTE_LICENSE_NAMES = ['폐기물처리업', '폐기물수집운반업', '폐기물재활용업']

# ── 상세사이트 주소 ──
KWATER_DETAIL_BASE = ("https://ebid.kwater.or.kr/wq/index.do"
                       "?w2xPath=/ui/index.xml"
                       "&view=bidpblanc/bidpblancsttus/BIDBD32000002.xml"
                       "&tndrPbanno=")
KOGAS_HOME = "https://k-ebid.kogas.or.kr"
D2B_HOME   = "https://www.d2b.go.kr/"
LH_HOME    = "https://ebid.lh.or.kr/"

# ── 테스트 모드 (True: 필터 OFF → 전체 노출) ──
TEST_MODE = True   # ← 실운영 시 False 로 변경


# =====================================================================
# 1. 지역·면허 필터 함수
# =====================================================================
REGION_FREE = ['전국', '제한없음']

def _region_token_pass(token: str) -> bool:
    token = token.strip()
    if not token:
        return True
    if any(f in token for f in REGION_FREE):
        return True
    if '평택' in token or '화성' in token:
        return True
    if token == '경기도':
        return True
    return False

def region_pass(region_text) -> bool:
    if TEST_MODE:
        return True
    if region_text is None:
        return True
    if isinstance(region_text, (list, tuple, set)):
        tokens = list(region_text)
    else:
        text = str(region_text).strip()
        if not text:
            return True
        tokens = re.split(r'[,]', text)
    return any(_region_token_pass(t) for t in tokens) if tokens else True

def license_code_pass(license_text) -> bool:
    if TEST_MODE:
        return True
    if not license_text:
        return True
    text = str(license_text).strip()
    if not text:
        return True
    return any(code in text for code in OUR_LICENSES)

def lh_license_pass(item) -> bool:
    if TEST_MODE:
        return True
    for n in range(1, 11):
        slots = [lh_clean(item.findtext(f'req{n}Reqlic{m}Nm')) for m in range(1, 11)]
        slots = [s for s in slots if s]
        if not slots:
            continue
        if not any(name in s for s in slots for name in WASTE_LICENSE_NAMES):
            return False
    return True


# =====================================================================
# 2. 공통 행 구조
# =====================================================================
def to_row(source, notice_no, title, agency, notice_dt, close_dt, open_dt,
           amount, region, license_info, keyword, url='', extra=''):
    return {
        '출처기관':     source,
        '공고번호':     notice_no,
        '공고명':      title,
        '수요/발주기관': agency,
        '공고일시':     notice_dt,
        '마감일시':     close_dt,
        '개찰일시':     open_dt,
        '금액(원)':     amount,
        '지역제한':     region,
        '면허정보':     license_info,
        '매칭키워드':   keyword,
        '상세URL':     url,
        '비고':        extra,
    }

def format_d2b_dt(val):
    if not val or str(val).strip() in ('', '-'):
        return '-'
    s = str(val).replace('.0', '').strip()
    try:
        if len(s) >= 12:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
        elif len(s) >= 8:
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        return s
    except Exception:
        return s


# =====================================================================
# 3. 나라장터 (G2B, JSON) ── 병렬 상세 조회
# =====================================================================
def fetch_narajangter():
    print("🔍 [나라장터] 검색 중...")
    service_key = unquote(SERVICE_KEY)
    s_date = SEARCH_START.strftime("%Y%m%d0000")
    e_date = SEARCH_END.strftime("%Y%m%d2359")
    url_base = 'https://apis.data.go.kr/1230000/ad/BidPublicInfoService/'

    all_raw = []
    total_kw = len(KEYWORDS)
    for kidx, kw in enumerate(KEYWORDS, 1):
        sys.stdout.write(f"\r   [나라장터] 키워드 {kidx}/{total_kw} ('{kw}')      ")
        sys.stdout.flush()
        try:
            res = requests.get(url_base + 'getBidPblancListInfoServcPPSSrch',
                params={'serviceKey': service_key, 'numOfRows': '100', 'type': 'json',
                        'inqryDiv': '1', 'inqryBgnDt': s_date, 'inqryEndDt': e_date,
                        'bidNtceNm': kw}, timeout=10)
            items = res.json().get('response', {}).get('body', {}).get('items', [])
            if items:
                for it in ([items] if isinstance(items, dict) else items):
                    it['_keyword'] = kw
                    all_raw.append(it)
        except Exception as e:
            print(f"\n   ⚠️ 나라장터 '{kw}' 오류: {e}")
    print()

    if not all_raw:
        print("   ⚠️ 나라장터: 검색된 공고 없음")
        return []

    df_bids = pd.DataFrame(all_raw).drop_duplicates(subset=['bidNtceNo'])
    total_rows = len(df_bids)
    print(f"   [나라장터] {total_rows}건 → 지역·면허 병렬 조회 (20 스레드)...")

    def fetch_detail(row):
        b_no  = row['bidNtceNo']
        b_ord = str(row.get('bidNtceOrd', '000')).zfill(3)
        base_p = {'ServiceKey': service_key, 'type': 'json', 'inqryDiv': '2',
                  'bidNtceNo': b_no, 'bidNtceOrd': b_ord}

        # 참가가능지역
        region_val = "확인불가"
        try:
            r_res = requests.get(url_base + 'getBidPblancListInfoPrtcptPsblRgn',
                                 params=base_p, timeout=8).json()
            r_items = r_res.get('response', {}).get('body', {}).get('items', [])
            regs = [str(ri.get('prtcptPsblRgnNm', ''))
                    for ri in ([r_items] if isinstance(r_items, dict) else r_items)
                    if ri.get('prtcptPsblRgnNm')]
            region_val = ", ".join(set(regs)) if regs else "제한없음"
        except Exception:
            pass

        if region_val != "확인불가" and not region_pass(region_val):
            return None

        # 참가가능업종(면허)
        license_val = "확인불가"
        try:
            l_res = requests.get(url_base + 'getBidPblancListInfoLicenseLimit',
                                 params=base_p, timeout=8).json()
            l_items = l_res.get('response', {}).get('body', {}).get('items', [])
            # lcnsLmtNm(면허명)과 permsnIndstrytyList(허가업종) 둘 다 수집
            lics = []
            for li in ([l_items] if isinstance(l_items, dict) else l_items):
                v = li.get('lcnsLmtNm') or li.get('permsnIndstrytyList', '')
                if v:
                    lics.append(str(v))
            license_val = " / ".join(set(lics)) if lics else "제한없음"
        except Exception:
            pass

        if license_val not in ("확인불가", "제한없음") and not license_code_pass(license_val):
            return None

        return to_row(
            source='나라장터', notice_no=b_no,
            title=row.get('bidNtceNm', '-'),
            agency=row.get('dminsttNm', '-'),
            notice_dt=row.get('bidNtceDate', row.get('rgstDt', '-')),
            close_dt=row.get('bidClseDt', '-'),
            open_dt=row.get('opengDt', '-'),
            amount=row.get('asignBdgtAmt', row.get('bdgtAmt', '-')),
            region=region_val,
            license_info=license_val,
            keyword=row.get('_keyword', '-'),
            url=row.get('bidNtceDtlUrl', '-'),
        )

    rows_list = [row for _, row in df_bids.reset_index(drop=True).iterrows()]
    results, done = [], 0
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_detail, row): row for row in rows_list}
        for future in as_completed(futures):
            done += 1
            sys.stdout.write(f"\r   [나라장터] 상세조회 {done}/{total_rows}      ")
            sys.stdout.flush()
            try:
                r = future.result()
                if r:
                    results.append(r)
            except Exception:
                pass

    print()
    print(f"   ✅ 나라장터: {len(results)}건")
    return results


# =====================================================================
# 4. 국방부 (D2B) ── 전체 조회 후 공고일자 로컬 필터 (원본 방식 복원)
#    ⚠️ anmtDateBegin/End 서버 파라미터가 실제 동작 안 함 → 로컬 필터링
# =====================================================================
def fetch_d2b():
    """
    일반경쟁: 전체 조회 → pblancDate(공고일자)로 7일 필터 (로컬)
    공개수의: 전체 조회 → ntatPlanDate(개찰예정일)로 7일 필터 (로컬)
             ⚠️ 공고일자 필드 없음, 차선책으로 개찰예정일 기준
    """
    print("🔍 [국방부] 검색 중...")
    results   = []
    start_day = SEARCH_START.strftime("%Y%m%d")
    end_day   = SEARCH_END.strftime("%Y%m%d")
    total_kw  = len(KEYWORDS)

    # ① 일반경쟁
    url_list = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancList"
    url_det  = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcCmpetBidPblancDetail"
    for idx, kw in enumerate(KEYWORDS, 1):
        sys.stdout.write(f"\r   [국방부-일반경쟁] {idx}/{total_kw} ('{kw}')      ")
        sys.stdout.flush()
        try:
            res = requests.get(url_list,
                params={'serviceKey': SERVICE_KEY, 'numOfRows': '400',
                        '_type': 'json', 'bidNm': kw},
                headers=HEADERS, timeout=15)
            items = res.json().get('response',{}).get('body',{}).get('items',{}).get('item',[])
            items = [items] if isinstance(items, dict) else (items or [])
            for it in items:
                pblanc_dt = str(it.get('pblancDate','')).replace('.0','').strip()[:8]
                if pblanc_dt and not (start_day <= pblanc_dt <= end_day):
                    continue  # 7일 외 공고 제외

                p_det = {'serviceKey': SERVICE_KEY, '_type': 'json',
                         'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'),
                         'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'),
                         'dcsNo': it.get('dcsNo')}
                area, open_dt, budget, g2b_no, lcns = "제한없음", it.get('opengDt','-'), it.get('budgetAmount',0), None, ""
                try:
                    det = requests.get(url_det, params=p_det, headers=HEADERS, timeout=8) \
                               .json().get('response',{}).get('body',{}).get('item',{})
                    area    = det.get('areaLmttList') or "제한없음"
                    open_dt = det.get('opengDt') or open_dt
                    budget  = det.get('budgetAmount') or budget
                    g2b_no  = det.get('g2bPblancNo')
                    lcns    = det.get('lcnsLmttList') or "제한없음"
                except Exception:
                    pass

                if not region_pass(area):
                    continue
                if lcns not in ("", "제한없음") and not license_code_pass(lcns):
                    continue

                results.append(to_row(
                    source='국방부(일반경쟁)',
                    notice_no=g2b_no or it.get('pblancNo', '-'),
                    title=it.get('bidNm',''),
                    agency=it.get('ornt','-'),
                    notice_dt=format_d2b_dt(it.get('pblancDate','-')),
                    close_dt=format_d2b_dt(it.get('biddocPresentnClosDt','-')),
                    open_dt=format_d2b_dt(open_dt),
                    amount=budget, region=area, license_info=lcns,
                    keyword=kw, url=D2B_HOME,
                ))
        except Exception as e:
            print(f"\n   ⚠️ 국방부 일반경쟁 '{kw}' 오류: {e}")
    print()

    # ② 공개수의
    url_priv     = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanList"
    url_priv_det = "http://openapi.d2b.go.kr/openapi/service/BidPblancInfoService/getDmstcOthbcVltrnNtatPlanDetail"
    for idx, kw in enumerate(KEYWORDS, 1):
        sys.stdout.write(f"\r   [국방부-공개수의] {idx}/{total_kw} ('{kw}')      ")
        sys.stdout.flush()
        try:
            res = requests.get(url_priv,
                params={'serviceKey': SERVICE_KEY, 'numOfRows': '400',
                        '_type': 'json', 'othbcNtatNm': kw},
                headers=HEADERS, timeout=15)
            items = res.json().get('response',{}).get('body',{}).get('items',{}).get('item',[])
            items = [items] if isinstance(items, dict) else (items or [])
            for it in items:
                # 공개수의는 공고일자 필드 없음 → ntatPlanDate(개찰예정일)로 대체
                plan_dt = str(it.get('ntatPlanDate','')).replace('.0','').strip()[:8]
                if plan_dt and not (start_day <= plan_dt <= end_day):
                    continue

                p_det = {'serviceKey': SERVICE_KEY, '_type': 'json',
                         'pblancNo': it.get('pblancNo'), 'pblancOdr': it.get('pblancOdr'),
                         'demandYear': it.get('demandYear'), 'orntCode': it.get('orntCode'),
                         'dcsNo': it.get('dcsNo'), 'iemNo': it.get('iemNo'),
                         'ntatPlanDate': it.get('ntatPlanDate')}
                area, open_dt, budget, g2b_no, lcns = "제한없음", it.get('opengDt','-'), it.get('budgetAmount',0), None, ""
                try:
                    det = requests.get(url_priv_det, params=p_det, headers=HEADERS, timeout=8) \
                               .json().get('response',{}).get('body',{}).get('item',{})
                    area    = det.get('areaLmttList') or "제한없음"
                    open_dt = det.get('opengDt') or open_dt
                    budget  = det.get('budgetAmount') or budget
                    g2b_no  = det.get('g2bPblancNo')
                    lcns    = det.get('lcnsLmttList') or "제한없음"
                except Exception:
                    pass

                if not region_pass(area):
                    continue
                if lcns not in ("", "제한없음") and not license_code_pass(lcns):
                    continue

                results.append(to_row(
                    source='국방부(공개수의)',
                    notice_no=g2b_no or it.get('pblancNo','-'),
                    title=it.get('othbcNtatNm',''),
                    agency=it.get('ornt','-'),
                    notice_dt='-',  # 공개수의는 공고일자 필드 없음
                    close_dt=format_d2b_dt(it.get('prqudoPresentnClosDt','-')),
                    open_dt=format_d2b_dt(open_dt),
                    amount=budget, region=area, license_info=lcns,
                    keyword=kw, url=D2B_HOME,
                    extra='⚠️개찰예정일 기준 필터(공고일자 파라미터 없음)',
                ))
        except Exception as e:
            print(f"\n   ⚠️ 국방부 공개수의 '{kw}' 오류: {e}")
    print()

    # 중복 제거
    seen, dedup = set(), []
    for r in results:
        key = (r['출처기관'], r['공고번호'])
        if key not in seen:
            seen.add(key); dedup.append(r)
        else:
            for d in dedup:
                if (d['출처기관'], d['공고번호']) == key and r['매칭키워드'] not in d['매칭키워드']:
                    d['매칭키워드'] += f",{r['매칭키워드']}"

    print(f"   ✅ 국방부: {len(dedup)}건")
    return dedup


# =====================================================================
# 5. LH (XML)
# =====================================================================
def lh_clean(text):
    return re.sub(r'<!\[CDATA\[|\]\]>', '', text).strip() if text else ""

def fetch_lh():
    print("🔍 [LH] 검색 중...")
    results   = []
    url       = "http://openapi.ebid.lh.or.kr/ebid.com.openapi.service.OpenBidInfoList.dev"
    start_day = SEARCH_START.strftime("%Y%m%d")
    end_day   = SEARCH_END.strftime("%Y%m%d")
    params = {'serviceKey': SERVICE_KEY, 'numOfRows': '500', 'pageNo': '1',
              'tndrbidRegDtStart': start_day, 'tndrbidRegDtEnd': end_day}
    try:
        response = requests.get(url, params=params, timeout=20)
        response.encoding = response.apparent_encoding
        clean_xml = re.sub(r'<\?xml.*\?>', '', response.text)
        if "<resultCode>00</resultCode>" not in clean_xml:
            print(f"   ⚠️ LH 서버 응답 에러: {clean_xml[:150]}")
            return results
        root = ET.fromstring(f"<root>{clean_xml}</root>")
        all_items = root.findall('.//item')
        total = len(all_items)
        for idx, item in enumerate(all_items, 1):
            sys.stdout.write(f"\r   [LH] {idx}/{total}      ")
            sys.stdout.flush()
            title = lh_clean(item.findtext('bidnmKor'))
            matched = [kw for kw in KEYWORDS if kw in title]
            if not matched:
                continue

            region_tokens = [(item.findtext(f'zoneRstrct{n}') or '').strip() for n in range(1, 5)]
            region = " ".join(filter(None, region_tokens))
            if not region_pass(region_tokens):
                continue
            if not lh_license_pass(item):
                continue

            license_summary = "/".join(sorted(set(
                lh_clean(item.findtext(f'req{n}Reqlic{m}Nm'))
                for n in range(1, 11) for m in range(1, 11)
                if lh_clean(item.findtext(f'req{n}Reqlic{m}Nm'))
            ))) or '제한없음'

            results.append(to_row(
                source='LH', notice_no=item.findtext('bidNum'), title=title,
                agency=lh_clean(item.findtext('zoneHqCd')),
                notice_dt=item.findtext('tndrbidRegDt'),
                close_dt=item.findtext('tndrdocAcptEndDtm'),
                open_dt=item.findtext('openDtm'),
                amount=item.findtext('fdmtlAmt'),
                region=region if region else '제한없음',
                license_info=license_summary,
                keyword=','.join(matched), url=LH_HOME,
            ))
    except Exception as e:
        print(f"\n   ⚠️ LH 오류: {e}")
    print()
    print(f"   ✅ LH: {len(results)}건")
    return results


# =====================================================================
# 6. 가스공사 (XML) ── DOCDATE_END 정식 파라미터 확인됨 (이미지4)
# =====================================================================
def fetch_kogas():
    print("🔍 [가스공사] 검색 중... (지역·면허 필드 없음 → 필터 미적용)")
    results    = []
    base_url   = "http://apis.data.go.kr/B551210/bidInfoList/getBidInfoList"
    start_date = SEARCH_START.strftime("%Y%m%d")
    end_date   = SEARCH_END.strftime("%Y%m%d")
    params = {'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '500',
              'DOCDATE_START': start_date, 'DOCDATE_END': end_date}
    try:
        res = requests.get(base_url, params=params, headers=HEADERS, timeout=15)
        if res.status_code != 200:
            print(f"   ⚠️ 가스공사 응답 에러 (코드: {res.status_code})")
            return results
        root = ET.fromstring(res.text)
        all_items = root.findall('.//item')
        total = len(all_items)
        for idx, item in enumerate(all_items, 1):
            sys.stdout.write(f"\r   [가스공사] {idx}/{total}      ")
            sys.stdout.flush()
            title = item.findtext('NOTICE_NAME') or '-'
            matched = [kw for kw in KEYWORDS if kw in title]
            if not matched:
                continue
            # DOCDATE_END 미작동 대비 2차 날짜 필터
            notice_dt = (item.findtext('NOTICE_DT') or '').replace('-','')[:8]
            if notice_dt and not (start_date <= notice_dt <= end_date):
                continue
            results.append(to_row(
                source='가스공사',
                notice_no=item.findtext('NOTICE_CODE') or '-', title=title,
                agency=item.findtext('CONT_METHOD_NAME') or '-',
                notice_dt=item.findtext('NOTICE_DT') or '-',
                close_dt=item.findtext('END_DT') or '-',
                open_dt='-', amount='-',
                region='확인불가(매뉴얼 미확인)',
                license_info='확인불가(매뉴얼 미확인)',
                keyword=','.join(matched), url=KOGAS_HOME,
            ))
    except Exception as e:
        print(f"\n   ⚠️ 가스공사 오류: {e}")
    print()
    print(f"   ✅ 가스공사: {len(results)}건")
    return results


# =====================================================================
# 7. 수자원공사 (JSON) ── searchDt(YYYYMM)만 지원, 일별 범위 없음(이미지3 확인)
# =====================================================================
def fetch_kwater():
    print("🔍 [수자원공사] 검색 중... (월 단위 조회, 지역·면허 필드 없음 → 필터 미적용)")
    results      = []
    base_url     = "http://apis.data.go.kr/B500001/ebid/tndr3/servcList"
    search_month = TODAY.strftime('%Y%m')
    for kidx, kw in enumerate(KEYWORDS, 1):
        sys.stdout.write(f"\r   [수자원공사] {kidx}/{len(KEYWORDS)} ('{kw}')      ")
        sys.stdout.flush()
        try:
            res = requests.get(base_url,
                params={'serviceKey': SERVICE_KEY, 'pageNo': '1', 'numOfRows': '100',
                        '_type': 'json', 'searchDt': search_month, 'bidNm': kw},
                headers=HEADERS, timeout=10)
            if res.status_code != 200:
                continue
            items = res.json().get('response',{}).get('body',{}).get('items',{}).get('item',[])
            items = [items] if isinstance(items, dict) else (items or [])
            for it in items:
                title = it.get('tndrPblancNm', '-')
                if kw not in title:
                    continue
                results.append(to_row(
                    source='수자원공사',
                    notice_no=it.get('tndrPbanno','-'), title=title,
                    agency=it.get('cntrctDeptNm','-'),
                    notice_dt='-',
                    close_dt=it.get('tndrPblancEnddt','-'),
                    open_dt='-', amount='-',
                    region='확인불가(매뉴얼 미확인)',
                    license_info='확인불가(매뉴얼 미확인)',
                    keyword=kw,
                    url=(KWATER_DETAIL_BASE + str(it.get('tndrPbanno','')))
                        if it.get('tndrPbanno') else '-',
                ))
        except Exception as e:
            print(f"\n   ⚠️ 수자원공사 '{kw}' 오류: {e}")
    print()

    seen, dedup = set(), []
    for r in results:
        if r['공고번호'] not in seen:
            seen.add(r['공고번호']); dedup.append(r)
    print(f"   ✅ 수자원공사: {len(dedup)}건")
    return dedup


# =====================================================================
# 메인
# =====================================================================
def main():
    mode_str = "테스트(필터OFF)" if TEST_MODE else "실운영(필터ON)"
    print(f"\n{'='*70}")
    print(f"🚀 통합 입찰공고 검색 [{mode_str}]")
    print(f"📅 검색기간: {SEARCH_START:%Y-%m-%d} ~ {SEARCH_END:%Y-%m-%d}")
    print(f"🎯 키워드({len(KEYWORDS)}개): {', '.join(KEYWORDS)}")
    print(f"📍 지역필터: 경기도/평택/화성/전국(제한없음) → {'OFF' if TEST_MODE else 'ON'}")
    print(f"🪪 면허필터: 코드{OUR_LICENSES} / LH명칭{WASTE_LICENSE_NAMES} → {'OFF' if TEST_MODE else 'ON'}")
    print("💡 윈도우 창 멈춤 방지: cmd 제목줄 우클릭 → 속성 → 빠른 편집 모드 체크 해제")
    print(f"{'='*70}\n")

    all_results = []
    fetchers = [
        ('나라장터',  fetch_narajangter),
        ('국방부',    fetch_d2b),
        ('LH',       fetch_lh),
        ('가스공사',  fetch_kogas),
        ('수자원공사', fetch_kwater),
    ]
    total_agency = len(fetchers)
    for aidx, (name, fn) in enumerate(fetchers, 1):
        print(f"\n[전체 {aidx}/{total_agency}] {name} 시작 ({(aidx-1)*20}% 완료)")
        try:
            all_results.extend(fn())
        except Exception:
            print(f"🚨 {name} 치명적 오류:")
            traceback.print_exc()
    print(f"\n[전체 {total_agency}/{total_agency}] 완료 (100%)")

    if not all_results:
        print("\n⚠️ 조건에 맞는 공고가 없습니다.")
        input("\n엔터를 누르면 종료됩니다.")
        return

    df = pd.DataFrame(all_results)
    filename = f"통합_입찰공고_{mode_str}_{TODAY:%Y%m%d_%H%M}.xlsx"
    with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='통합결과', index=False)
        for src in df['출처기관'].unique():
            df[df['출처기관']==src].to_excel(
                writer, sheet_name=re.sub(r'[\\/*?:\[\]]','',src)[:31], index=False)
        wb = writer.book
        hfmt = wb.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#1F4E78',
                               'border': 1, 'align': 'center', 'valign': 'vcenter'})
        for ws in writer.sheets.values():
            ws.freeze_panes(1, 0)
            ws.set_default_row(20)
            for ci, col in enumerate(df.columns):
                ws.write(0, ci, col, hfmt)
                ws.set_column(ci, ci, 22)

    print(f"\n{'='*70}")
    print(f"🎯 완료! 총 {len(df)}건")
    print(df['출처기관'].value_counts().to_string())
    print(f"📁 파일: {filename}")
    print(f"{'='*70}")
    input("\n엔터를 누르면 종료됩니다.")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\n" + "="*70)
        print("🚨 예상치 못한 오류가 발생했습니다. 아래 내용을 캡처해주세요:")
        print("="*70)
        traceback.print_exc()
        input("\n엔터를 누르면 종료됩니다.")
