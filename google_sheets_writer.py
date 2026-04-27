#!/usr/bin/env python3
"""
Re:NK Google Sheets 데이터 아카이빙
=====================================
매체별 시트에 일별 데이터 행을 자동 추가

시트 구조:
  - META 자사몰      : 날짜, 광고비, 노출, 클릭, 구매, 매출, ROAS, CTR, CPC, CPM, CPA
  - META 스마트스토어 : 날짜, 광고비, 노출, 클릭, CPAS전환값, CPAS구매, ROAS, CTR, CPC, CPM
  - 네이버 SA        : 날짜, 총광고비, 총클릭, 총전환, 브검_광고비, 브검_클릭, 파워링크_광고비, 파워링크_클릭, 쇼검_광고비, 쇼검_클릭
  - 카페24 커머스     : 날짜, 순매출, 주문건수, 구매자수, 객단가, 상품금액, 할인, 쿠폰, 배송비

셋업 필수:
  1. Google Cloud Console → Google Sheets API 활성화
  2. 서비스 계정 생성 → JSON 키 다운로드 → google_sheets_key.json 으로 저장
     또는 기존 OAuth 인증 사용 (google_ads_credentials.json과 동일)
  3. 스프레드시트 생성 후 서비스 계정 이메일에 편집 권한 공유
  4. google_sheets_config.json에 스프레드시트 ID 기입

사용법:
  python google_sheets_writer.py --test          # 연결 테스트
  python google_sheets_writer.py --init          # 시트 헤더 자동 생성
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime


# ============================================================
# 설정
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 서비스 계정 키 (권장) 또는 OAuth 인증
SERVICE_KEY_FILE = os.path.join(SCRIPT_DIR, 'config', 'renk_google_sheets_key.json')
OAUTH_CREDS_FILE = os.path.join(SCRIPT_DIR, 'config', 'renk_google_ads_credentials.json')
TOKEN_FILE = os.path.join(SCRIPT_DIR, 'config', 'renk_google_sheets_token.json')

# 스프레드시트 설정
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'config', 'renk_google_sheets_config.json')

SHEETS_API_BASE = 'https://sheets.googleapis.com/v4/spreadsheets'

# 시트별 헤더 정의
SHEET_HEADERS = {
    'META 자사몰': [
        '날짜', '광고비', '노출', '클릭', '구매', '매출(전환값)',
        'ROAS(%)', 'CTR(%)', 'CPC', 'CPM', 'CPA', '월', '주차',
    ],
    'META 스마트스토어': [
        '날짜', '광고비', '노출', '클릭', 'CPAS구매', 'CPAS전환값',
        'ROAS(%)', 'CTR(%)', 'CPC', 'CPM', '월', '주차',
    ],
    '네이버 SA': [
        '날짜', '총광고비', '총클릭', '구매완료 전환수', '구매완료 전환매출',
        '브검_광고비', '브검_클릭', '브검_전환',
        '파워링크_광고비', '파워링크_클릭', '파워링크_전환',
        '쇼검_광고비', '쇼검_클릭', '쇼검_전환', '월', '주차',
    ],
    '카페24 커머스': [
        '날짜', '결제합계', '환불합계', '순매출', '주문건수', '구매자수',
        '첫구매', '재구매', '첫구매비율(%)', '재구매비율(%)',
        '방문자수', '객단가', '상품구매금액', '월', '주차',
    ],
    '카페24 상품TOP': [
        '날짜', '순위', '상품명', '실결제금액', '판매수량', '주문건수', '월', '주차',
    ],
    'Google Ads': [
        '날짜', '광고비', '노출', '클릭', '구매', '매출(전환값)',
        'ROAS(%)', 'CTR(%)', 'CPC', 'CPM', 'CPA', '월', '주차',
    ],
    '스마트스토어 커머스': [
        '날짜', '결제합계', '환불합계', '순매출', '주문건수', '결제자수',
        '객단가', '월', '주차',
    ],
}


# ============================================================
# 인증
# ============================================================

def load_config() -> dict:
    """google_sheets_config.json 로드"""
    if not os.path.exists(CONFIG_FILE):
        print("[ERROR] google_sheets_config.json 파일 없음.")
        print("  아래 형식으로 생성하세요:")
        print('  { "spreadsheet_id": "스프레드시트_ID_여기에" }')
        return {}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_access_token_service_account() -> str:
    """서비스 계정 JSON 키 → Access Token (JWT 방식)"""
    import time
    import hashlib
    import hmac
    import base64

    if not os.path.exists(SERVICE_KEY_FILE):
        return ''

    with open(SERVICE_KEY_FILE, 'r') as f:
        key_data = json.load(f)

    # JWT 생성
    now = int(time.time())
    header = base64.urlsafe_b64encode(json.dumps({
        'alg': 'RS256', 'typ': 'JWT'
    }).encode()).rstrip(b'=').decode()

    payload = base64.urlsafe_b64encode(json.dumps({
        'iss': key_data['client_email'],
        'scope': 'https://www.googleapis.com/auth/spreadsheets',
        'aud': 'https://oauth2.googleapis.com/token',
        'iat': now,
        'exp': now + 3600,
    }).encode()).rstrip(b'=').decode()

    # RSA 서명 (cryptography 라이브러리 필요)
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        private_key = serialization.load_pem_private_key(
            key_data['private_key'].encode(), password=None
        )
        message = f"{header}.{payload}".encode()
        signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
        sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()
    except ImportError:
        print("[WARN] cryptography 라이브러리 없음 → pip install cryptography")
        print("  또는 OAuth 인증 방식을 사용하세요.")
        return ''

    jwt_token = f"{header}.{payload}.{sig_b64}"

    # JWT → Access Token
    data = urllib.parse.urlencode({
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': jwt_token,
    }).encode()

    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result.get('access_token', '')
    except Exception as e:
        print(f"[ERROR] 서비스 계정 토큰 발급 실패: {e}")
        return ''


def get_access_token_oauth() -> str:
    """OAuth Refresh Token → Access Token (Google Ads와 동일 인증 재사용)"""
    import time as _time

    if not os.path.exists(OAUTH_CREDS_FILE):
        return ''

    with open(OAUTH_CREDS_FILE, 'r') as f:
        creds = json.load(f)

    if not creds.get('refresh_token'):
        return ''

    # 캐시 확인
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            cached = json.load(f)
        if cached.get('expires_at', 0) > _time.time():
            return cached.get('access_token', '')

    data = urllib.parse.urlencode({
        'client_id': creds['client_id'],
        'client_secret': creds['client_secret'],
        'refresh_token': creds['refresh_token'],
        'grant_type': 'refresh_token',
    }).encode()

    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            result['expires_at'] = _time.time() + result.get('expires_in', 3600) - 60
            with open(TOKEN_FILE, 'w') as f:
                json.dump(result, f)
            return result.get('access_token', '')
    except Exception as e:
        print(f"[ERROR] OAuth 토큰 발급 실패: {e}")
        return ''


def get_access_token() -> str:
    """사용 가능한 인증 방식으로 토큰 발급"""
    # 서비스 계정 우선
    token = get_access_token_service_account()
    if token:
        return token
    # OAuth fallback
    token = get_access_token_oauth()
    if token:
        return token

    print("[ERROR] Google Sheets 인증 실패")
    print("  google_sheets_key.json (서비스 계정) 또는")
    print("  google_ads_credentials.json (OAuth) 중 하나가 필요합니다.")
    return ''


# ============================================================
# Sheets API 호출
# ============================================================

def _retry_on_429(func, max_retries=3, base_delay=15):
    """429 Rate Limit 시 자동 재시도 (지수 백오프)"""
    import time
    for attempt in range(max_retries + 1):
        result = func()
        if result is not None:
            return result
        if attempt < max_retries:
            delay = base_delay * (2 ** attempt)
            print(f"  [WAIT] Rate Limit — {delay}초 대기 후 재시도 ({attempt+1}/{max_retries})...")
            time.sleep(delay)
    return {}


def sheets_get(spreadsheet_id: str, range_str: str, token: str) -> dict:
    """Sheets API GET (값 읽기) — 429 자동 재시도"""
    url = f"{SHEETS_API_BASE}/{spreadsheet_id}/values/{urllib.parse.quote(range_str)}"

    def _call():
        req = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {token}',
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            if e.code == 429:
                return None  # 재시도 트리거
            print(f"[ERROR] Sheets GET ({range_str}, HTTP {e.code}): {body}")
            return {}
        except Exception as e:
            print(f"[ERROR] Sheets GET 예외: {e}")
            return {}

    return _retry_on_429(_call)


def sheets_append(spreadsheet_id: str, range_str: str, values: list, token: str) -> dict:
    """Sheets API APPEND (행 추가)"""
    url = (
        f"{SHEETS_API_BASE}/{spreadsheet_id}/values/"
        f"{urllib.parse.quote(range_str)}:append"
        f"?valueInputOption=USER_ENTERED&insertDataOption=OVERWRITE"
    )
    body = json.dumps({'values': values}).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        print(f"[ERROR] Sheets APPEND ({range_str}, HTTP {e.code}): {body_text}")
        return {}
    except Exception as e:
        print(f"[ERROR] Sheets APPEND 예외: {e}")
        return {}


def sheets_update(spreadsheet_id: str, range_str: str, values: list, token: str) -> dict:
    """Sheets API UPDATE (셀 덮어쓰기)"""
    url = (
        f"{SHEETS_API_BASE}/{spreadsheet_id}/values/"
        f"{urllib.parse.quote(range_str)}"
        f"?valueInputOption=USER_ENTERED"
    )
    body = json.dumps({'values': values}).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='PUT', headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        print(f"[ERROR] Sheets UPDATE ({range_str}, HTTP {e.code}): {body_text}")
        return {}
    except Exception as e:
        print(f"[ERROR] Sheets UPDATE 예외: {e}")
        return {}


def sheets_batch_update(spreadsheet_id: str, requests: list, token: str) -> dict:
    """Sheets API batchUpdate (시트 생성 등 구조 변경)"""
    url = f"{SHEETS_API_BASE}/{spreadsheet_id}:batchUpdate"
    body = json.dumps({'requests': requests}).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        print(f"[ERROR] batchUpdate (HTTP {e.code}): {body_text}")
        return {}


def get_sheet_names(spreadsheet_id: str, token: str) -> list:
    """스프레드시트의 시트 이름 목록"""
    url = f"{SHEETS_API_BASE}/{spreadsheet_id}?fields=sheets.properties.title"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return [s['properties']['title'] for s in result.get('sheets', [])]
    except Exception:
        return []


def get_sheet_id_map(spreadsheet_id: str, token: str) -> dict:
    """시트 이름 → sheetId 매핑"""
    url = f"{SHEETS_API_BASE}/{spreadsheet_id}?fields=sheets.properties(title,sheetId)"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return {
                s['properties']['title']: s['properties']['sheetId']
                for s in result.get('sheets', [])
            }
    except Exception:
        return {}


# ============================================================
# 중복 체크
# ============================================================

def check_date_and_next_row(spreadsheet_id: str, sheet_name: str, date_str: str, token: str) -> tuple:
    """
    해당 날짜가 이미 기입되어 있는지 확인 + 다음 행 번호 반환
    반환: (exists: bool, next_row: int, existing_row: int or None)
    exists=True면 이미 기입됨, existing_row는 해당 행 번호 (1-based)
    """
    result = sheets_get(spreadsheet_id, f"'{sheet_name}'!A:A", token)
    values = result.get('values', [])
    for i, row in enumerate(values):
        if row and row[0] == date_str:
            return True, max(len(values) + 1, 2), i + 1  # i+1 = 1-based row number
    # 최소 2행 (1행은 헤더)
    return False, max(len(values) + 1, 2), None


def check_row_is_zero(spreadsheet_id: str, sheet_name: str, row_num: int, token: str) -> bool:
    """해당 행의 B열(광고비/결제합계)이 0인지 확인"""
    result = sheets_get(spreadsheet_id, f"'{sheet_name}'!B{row_num}", token)
    values = result.get('values', [])
    if not values or not values[0]:
        return True
    try:
        return float(values[0][0]) == 0
    except (ValueError, IndexError):
        return False


# ============================================================
# 데이터 행 생성
# ============================================================

def _safe(v, default=0):
    """None/빈값 안전 변환"""
    if v is None:
        return default
    return v


def _div(a, b):
    return round(a / b, 2) if b else 0


def make_meta_own_row(date_str: str, m: dict, row: int) -> list:
    """
    META 자사몰 행 데이터
    A:날짜 B:광고비 C:노출 D:클릭 E:구매 F:매출 → 원본 수치
    G:ROAS H:CTR I:CPC J:CPM K:CPA → 스프레드시트 수식
    """
    n = row  # 행 번호
    return [
        date_str,
        int(_safe(m.get('cost'))),
        int(_safe(m.get('impressions'))),
        int(_safe(m.get('clicks'))),
        int(_safe(m.get('purchases'))),
        int(_safe(m.get('revenue'))),
        f'=ROUND(IF(B{n}>0,F{n}/B{n}*100,0),2)',       # ROAS(%) 소수점 2자리
        f'=ROUND(IF(C{n}>0,D{n}/C{n}*100,0),2)',      # CTR(%) 소수점 2자리
        f'=ROUND(IF(D{n}>0,B{n}/D{n},0),0)',            # CPC 정수
        f'=ROUND(IF(C{n}>0,B{n}/C{n}*1000,0),0)',      # CPM 정수
        f'=ROUND(IF(E{n}>0,B{n}/E{n},0),0)',            # CPA 정수
        f'=TEXT(A{n},"YYYY-MM")',                        # 월
        f'=MONTH(A{n})&"월-"&INT((DAY(A{n})-1)/7)+1&"주차"',  # 주차
    ]


def make_meta_ss_row(date_str: str, m: dict, row: int) -> list:
    """
    META 스마트스토어 행 데이터
    A:날짜 B:광고비 C:노출 D:클릭 E:CPAS전환값 F:CPAS구매 → 원본 수치
    G:ROAS H:CTR I:CPC J:CPM → 스프레드시트 수식
    """
    n = row
    return [
        date_str,
        int(_safe(m.get('cost'))),
        int(_safe(m.get('impressions'))),
        int(_safe(m.get('clicks'))),
        int(_safe(m.get('cpas_purchases'))),     # E: CPAS구매
        int(_safe(m.get('cpas_revenue'))),        # F: CPAS전환값
        f'=ROUND(IF(B{n}>0,F{n}/B{n}*100,0),2)',       # ROAS(%) = 전환값/광고비
        f'=ROUND(IF(C{n}>0,D{n}/C{n}*100,0),2)',      # CTR(%)
        f'=ROUND(IF(D{n}>0,B{n}/D{n},0),0)',            # CPC
        f'=ROUND(IF(C{n}>0,B{n}/C{n}*1000,0),0)',      # CPM
        f'=TEXT(A{n},"YYYY-MM")',                        # 월
        f'=MONTH(A{n})&"월-"&INT((DAY(A{n})-1)/7)+1&"주차"',  # 주차
    ]


def make_naver_row(date_str: str, nv: dict, row: int) -> list:
    """네이버 SA 행 데이터 (캠페인 타입별 합산)"""
    sa = nv.get('sa', {})
    by_type = nv.get('by_type', {})

    bs = by_type.get('브랜드검색', {})
    pl = by_type.get('파워링크', {})
    sc = by_type.get('쇼핑검색', {})

    n = row
    return [
        date_str,
        int(_safe(sa.get('cost'))),                    # B: 총광고비
        int(_safe(sa.get('clicks'))),                   # C: 총클릭
        int(_safe(sa.get('purchase_count'))),            # D: 구매완료 전환수
        int(_safe(sa.get('purchase_revenue'))),          # E: 구매완료 전환매출
        int(_safe(bs.get('cost'))),                     # F: 브검_광고비
        int(_safe(bs.get('clicks'))),                   # G: 브검_클릭
        int(_safe(bs.get('purchase_count'))),            # H: 브검_전환
        int(_safe(pl.get('cost'))),                     # I: 파워링크_광고비
        int(_safe(pl.get('clicks'))),                   # J: 파워링크_클릭
        int(_safe(pl.get('purchase_count'))),            # K: 파워링크_전환
        int(_safe(sc.get('cost'))),                     # L: 쇼검_광고비
        int(_safe(sc.get('clicks'))),                   # M: 쇼검_클릭
        int(_safe(sc.get('purchase_count'))),            # N: 쇼검_전환
        f'=TEXT(A{n},"YYYY-MM")',                       # O: 월
        f'=MONTH(A{n})&"월-"&INT((DAY(A{n})-1)/7)+1&"주차"',  # P: 주차
    ]


def make_google_ads_row(date_str: str, g: dict, row: int) -> list:
    """
    Google Ads 행 데이터 (META 자사몰과 동일 구조)
    A:날짜 B:광고비 C:노출 D:클릭 E:구매(전환) F:매출(전환값)
    G:ROAS H:CTR I:CPC J:CPM K:CPA → 스프레드시트 수식
    L:월 M:주차
    """
    n = row
    total = g.get('total', {})

    return [
        date_str,
        int(_safe(total.get('cost'))),                    # B: 광고비
        int(_safe(total.get('impressions'))),              # C: 노출
        int(_safe(total.get('clicks'))),                   # D: 클릭
        int(round(_safe(total.get('conversions'), 0))),    # E: 구매(전환)
        int(_safe(total.get('revenue'))),                  # F: 매출(전환값)
        f'=ROUND(IF(B{n}>0,F{n}/B{n}*100,0),2)',         # G: ROAS(%)
        f'=ROUND(IF(C{n}>0,D{n}/C{n}*100,0),2)',        # H: CTR(%)
        f'=ROUND(IF(D{n}>0,B{n}/D{n},0),0)',              # I: CPC
        f'=ROUND(IF(C{n}>0,B{n}/C{n}*1000,0),0)',        # J: CPM
        f'=ROUND(IF(E{n}>0,B{n}/E{n},0),0)',              # K: CPA
        f'=TEXT(A{n},"YYYY-MM")',                          # L: 월
        f'=MONTH(A{n})&"월-"&INT((DAY(A{n})-1)/7)+1&"주차"',  # M: 주차
    ]


def make_smartstore_row(date_str: str, ss: dict, row: int) -> list:
    """
    스마트스토어 커머스 행 데이터
    A:날짜 B:결제합계 C:환불합계 D:순매출(수식) E:주문건수 F:결제자수
    G:객단가(수식) H:월 I:주차
    """
    n = row
    return [
        date_str,                                           # A: 날짜
        int(_safe(ss.get('paid_amount'))),                  # B: 결제합계
        int(_safe(ss.get('refund_amount'))),                # C: 환불합계
        f'=B{n}-C{n}',                                     # D: 순매출 (수식)
        int(_safe(ss.get('order_count'))),                  # E: 주문건수
        int(_safe(ss.get('unique_customers'))),             # F: 결제자수
        f'=ROUND(IF(F{n}>0,D{n}/F{n},0),0)',              # G: 객단가 (수식)
        f'=TEXT(A{n},"YYYY-MM")',                           # H: 월
        f'=MONTH(A{n})&"월-"&INT((DAY(A{n})-1)/7)+1&"주차"',  # I: 주차
    ]


def make_cafe24_row(date_str: str, c: dict, row: int, top_products: list = None) -> list:
    """카페24 커머스 행 데이터 (Dashboard API / CSV 병합)"""
    n = row
    return [
        date_str,                                    # A: 날짜
        int(_safe(c.get('paid_amount'))),             # B: 결제합계
        int(_safe(c.get('refund_amount'))),           # C: 환불합계
        f'=B{n}-C{n}',                              # D: 순매출 (수식)
        int(_safe(c.get('order_count'))),             # E: 주문건수
        int(_safe(c.get('unique_customers'))),        # F: 구매자수
        int(_safe(c.get('first_buyers'))),            # G: 첫구매
        int(_safe(c.get('repeat_buyers'))),           # H: 재구매
        f'=ROUND(IF(G{n}+H{n}>0,G{n}/(G{n}+H{n})*100,0),1)',  # I: 첫구매비율(%)
        f'=ROUND(IF(G{n}+H{n}>0,H{n}/(G{n}+H{n})*100,0),1)',  # J: 재구매비율(%)
        int(_safe(c.get('visitor_count'))),           # K: 방문자수
        f'=ROUND(IF(E{n}>0,D{n}/E{n},0),0)',        # L: 객단가 (수식)
        int(_safe(c.get('product_amount'))),          # M: 상품구매금액
        f'=TEXT(A{n},"YYYY-MM")',                    # N: 월
        f'=MONTH(A{n})&"월-"&INT((DAY(A{n})-1)/7)+1&"주차"',  # O: 주차
    ]


def make_top_product_rows(date_str: str, top_products: list, start_row: int) -> list:
    """카페24 상품TOP 시트 행 데이터 (TOP 3 = 3행)"""
    rows = []
    for i, p in enumerate(top_products[:3]):
        n = start_row + i
        rows.append([
            date_str,                                           # A: 날짜
            i + 1,                                              # B: 순위
            p.get('product_name', ''),                          # C: 상품명
            int(p.get('amount', 0)),                            # D: 실결제금액
            int(p.get('quantity', 0)),                           # E: 판매수량
            int(p.get('order_count', 0)),                        # F: 주문건수
            f'=TEXT(A{n},"YYYY-MM")',                           # G: 월
            f'=MONTH(A{n})&"월-"&INT((DAY(A{n})-1)/7)+1&"주차"',  # H: 주차
        ])
    return rows


# ============================================================
# 메인: 일별 데이터 기입
# ============================================================

def append_daily_data(date_str: str, own: dict, ss: dict,
                       naver: dict, google: dict, cafe24: dict,
                       top_products: list = None,
                       smartstore: dict = None) -> bool:
    """
    Google Sheets에 일별 데이터 추가 (매체별 시트)
    run_daily.py에서 호출하는 메인 함수

    반환: True=성공, False=실패
    """
    config = load_config()
    if not config:
        return False

    sid = config.get('spreadsheet_id', '')
    if not sid:
        print("[ERROR] spreadsheet_id 미설정")
        return False

    token = get_access_token()
    if not token:
        return False

    # 시트 탭 자동 생성 (없으면 생성 + 헤더 기입)
    existing_sheets = get_sheet_names(sid, token)
    for sheet_name, headers in SHEET_HEADERS.items():
        if sheet_name not in existing_sheets:
            print(f"  [AUTO] 시트 '{sheet_name}' 생성 중...")
            sheets_batch_update(sid, [{
                'addSheet': {'properties': {'title': sheet_name}}
            }], token)
            sheets_update(sid, f"'{sheet_name}'!A1", [headers], token)
            print(f"  [AUTO] 시트 '{sheet_name}' 생성 + 헤더 기입 완료")

    success = True

    def _write_sheet(sheet_name, range_str, row_data, data_dict, cost_key='cost',
                     force_update=False):
        """시트 기입 공통 로직 — 0행이면 실제 데이터로 덮어쓰기, force=무조건 덮어쓰기"""
        nonlocal success
        exists, next_row, existing_row = check_date_and_next_row(sid, sheet_name, date_str, token)

        if exists:
            # force_update: 기존 값 무관하게 항상 덮어쓰기
            if force_update and existing_row:
                print(f"  [FORCE] {sheet_name} {date_str} — 기존 행 강제 갱신")
                result = sheets_update(sid, f"'{sheet_name}'!A{existing_row}", [row_data], token)
                if not result:
                    success = False
                return

            # 기존 행이 0이고 새 데이터가 있으면 → 덮어쓰기
            has_new_data = False
            if isinstance(data_dict, dict):
                # 중첩 구조 (naver: sa.cost, google: total.cost)
                if 'sa' in data_dict:
                    sa = data_dict.get('sa', {})
                    has_new_data = sa.get('cost', 0) > 0 or sa.get('impressions', 0) > 0 or sa.get('clicks', 0) > 0
                elif 'total' in data_dict:
                    total = data_dict.get('total', {})
                    has_new_data = total.get('cost', 0) > 0 or total.get('impressions', 0) > 0
                else:
                    has_new_data = data_dict.get(cost_key, 0) > 0 or data_dict.get('paid_amount', 0) > 0 or data_dict.get('order_count', 0) > 0

            if has_new_data and existing_row and check_row_is_zero(sid, sheet_name, existing_row, token):
                print(f"  [UPDATE] {sheet_name} {date_str} — 0행을 실제 데이터로 덮어쓰기")
                result = sheets_update(sid, f"'{sheet_name}'!A{existing_row}", [row_data], token)
                if not result:
                    success = False
            else:
                print(f"  [SKIP] {sheet_name} {date_str} 이미 존재")
        else:
            result = sheets_append(sid, range_str, [row_data], token)
            if not result:
                success = False

    # META 자사몰
    exists_check, nr, er = check_date_and_next_row(sid, 'META 자사몰', date_str, token)
    row_num = er if (exists_check and er) else nr
    _write_sheet('META 자사몰', "'META 자사몰'!A:M",
                 make_meta_own_row(date_str, own or {}, row_num), own or {})

    # META 스마트스토어
    exists_check, nr, er = check_date_and_next_row(sid, 'META 스마트스토어', date_str, token)
    row_num = er if (exists_check and er) else nr
    _write_sheet('META 스마트스토어', "'META 스마트스토어'!A:L",
                 make_meta_ss_row(date_str, ss or {}, row_num), ss or {})

    # 네이버 SA
    exists_check, nr, er = check_date_and_next_row(sid, '네이버 SA', date_str, token)
    row_num = er if (exists_check and er) else nr
    _write_sheet('네이버 SA', "'네이버 SA'!A:P",
                 make_naver_row(date_str, naver or {}, row_num), naver or {})

    # Google Ads
    exists_check, nr, er = check_date_and_next_row(sid, 'Google Ads', date_str, token)
    row_num = er if (exists_check and er) else nr
    _write_sheet('Google Ads', "'Google Ads'!A:M",
                 make_google_ads_row(date_str, google or {}, row_num), google or {})

    # 카페24 커머스
    exists_check, nr, er = check_date_and_next_row(sid, '카페24 커머스', date_str, token)
    row_num = er if (exists_check and er) else nr
    _write_sheet('카페24 커머스', "'카페24 커머스'!A:O",
                 make_cafe24_row(date_str, cafe24 or {}, row_num), cafe24 or {}, 'paid_amount')

    # 스마트스토어 커머스
    exists_check, nr, er = check_date_and_next_row(sid, '스마트스토어 커머스', date_str, token)
    row_num = er if (exists_check and er) else nr
    _write_sheet('스마트스토어 커머스', "'스마트스토어 커머스'!A:I",
                 make_smartstore_row(date_str, smartstore or {}, row_num), smartstore or {}, 'paid_amount',
                 force_update=True)

    # 카페24 상품TOP (별도 시트, TOP 3 = 3행)
    if top_products:
        tp_exists, tp_nr, _ = check_date_and_next_row(sid, '카페24 상품TOP', date_str, token)
        if not tp_exists:
            tp_rows = make_top_product_rows(date_str, top_products, tp_nr)
            if tp_rows:
                result = sheets_append(sid, "'카페24 상품TOP'!A:H", tp_rows, token)
                if result:
                    print(f"  [OK] 카페24 상품TOP {date_str} — {len(tp_rows)}건 기입")
                else:
                    success = False
        else:
            print(f"  [SKIP] 카페24 상품TOP {date_str} 이미 존재")

    return success


# ============================================================
# 초기화: 시트 + 헤더 자동 생성
def _fmt_request(sheet_id: int, start_col: int, end_col: int, pattern: str) -> dict:
    """셀 서식 적용 요청 생성 (2행~1000행)"""
    # 날짜 패턴이면 DATE 타입, 아니면 NUMBER
    fmt_type = 'DATE' if 'yy' in pattern else 'NUMBER'
    return {
        'repeatCell': {
            'range': {
                'sheetId': sheet_id,
                'startRowIndex': 1,       # 헤더 제외
                'endRowIndex': 1000,
                'startColumnIndex': start_col,
                'endColumnIndex': end_col,
            },
            'cell': {
                'userEnteredFormat': {
                    'numberFormat': {'type': fmt_type, 'pattern': pattern}
                }
            },
            'fields': 'userEnteredFormat.numberFormat',
        }
    }


# 시트별 열 서식 정의: (시작열, 끝열, 패턴)
# 열 인덱스: A=0, B=1, C=2, ...
SHEET_FORMATS = {
    'META 자사몰': [
        (0, 1, 'yyyy-mm-dd'),  # A: 날짜
        (1, 6, '#,##0'),       # B~F: 광고비,노출,클릭,구매,매출 → 정수+콤마
        (6, 8, '#,##0.00'),    # G~H: ROAS,CTR → 소수점2자리+콤마
        (8, 11, '#,##0'),      # I~K: CPC,CPM,CPA → 정수+콤마
    ],
    'META 스마트스토어': [
        (0, 1, 'yyyy-mm-dd'),
        (1, 6, '#,##0'),
        (6, 8, '#,##0.00'),
        (8, 10, '#,##0'),
    ],
    '네이버 SA': [
        (0, 1, 'yyyy-mm-dd'),
        (1, 14, '#,##0'),
    ],
    '카페24 커머스': [
        (0, 1, 'yyyy-mm-dd'),
        (1, 9, '#,##0'),       # B~H: 결제합계~재구매
        (8, 10, '#,##0.0'),    # I~J: 첫구매비율,재구매비율
        (10, 13, '#,##0'),     # K~M: 방문자수,객단가,상품구매금액
    ],
    '카페24 상품TOP': [
        (0, 1, 'yyyy-mm-dd'),  # A: 날짜
        (1, 2, '#,##0'),       # B: 순위
        (3, 4, '#,##0'),       # D: 실결제금액
        (4, 6, '#,##0'),       # E~F: 판매수량, 주문건수
    ],
    '스마트스토어 커머스': [
        (0, 1, 'yyyy-mm-dd'),  # A: 날짜
        (1, 7, '#,##0'),       # B~G: 결제합계~객단가 → 정수+콤마
    ],
    'Google Ads': [
        (0, 1, 'yyyy-mm-dd'),  # A: 날짜
        (1, 6, '#,##0'),       # B~F: 광고비,노출,클릭,구매,매출 → 정수+콤마
        (6, 8, '#,##0.00'),    # G~H: ROAS,CTR → 소수점2자리+콤마
        (8, 11, '#,##0'),      # I~K: CPC,CPM,CPA → 정수+콤마
    ],
}


def initialize_sheets():
    """스프레드시트에 매체별 시트와 헤더를 자동 생성 + 숫자 서식 적용"""
    config = load_config()
    if not config:
        return False

    sid = config.get('spreadsheet_id', '')
    token = get_access_token()
    if not sid or not token:
        return False

    existing = get_sheet_names(sid, token)
    print(f"기존 시트: {existing}")

    for sheet_name, headers in SHEET_HEADERS.items():
        # 시트 생성
        if sheet_name not in existing:
            print(f"  시트 생성: {sheet_name}")
            sheets_batch_update(sid, [{
                'addSheet': {'properties': {'title': sheet_name}}
            }], token)

        # 헤더 기입
        sheets_update(sid, f"'{sheet_name}'!A1", [headers], token)
        print(f"  헤더 기입: {sheet_name} ({len(headers)}열)")

    # 숫자 서식 적용
    print("\n숫자 서식 적용 중...")
    id_map = get_sheet_id_map(sid, token)
    fmt_requests = []

    for sheet_name, formats in SHEET_FORMATS.items():
        sheet_id = id_map.get(sheet_name)
        if sheet_id is None:
            print(f"  [SKIP] {sheet_name} sheetId 없음")
            continue
        for start_col, end_col, pattern in formats:
            fmt_requests.append(_fmt_request(sheet_id, start_col, end_col, pattern))
        print(f"  {sheet_name}: 서식 적용")

    # 가운데 정렬 (헤더 포함 전체)
    for sheet_name in SHEET_HEADERS:
        sheet_id = id_map.get(sheet_name)
        if sheet_id is None:
            continue
        fmt_requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': 0,
                    'endRowIndex': 1000,
                },
                'cell': {
                    'userEnteredFormat': {
                        'horizontalAlignment': 'CENTER',
                    }
                },
                'fields': 'userEnteredFormat.horizontalAlignment',
            }
        })

    if fmt_requests:
        sheets_batch_update(sid, fmt_requests, token)
        print("서식 적용 완료! (숫자 포맷 + 가운데 정렬)")

    print("\n초기화 완료!")
    return True


# ============================================================
# 테스트
# ============================================================

def test_connection():
    print("=" * 50)
    print("Google Sheets API 연결 테스트")
    print("=" * 50)

    config = load_config()
    if not config:
        print("✗ google_sheets_config.json 없음")
        return False

    sid = config.get('spreadsheet_id', '')
    if not sid:
        print("✗ spreadsheet_id 미설정")
        return False

    print(f"✓ 스프레드시트 ID: {sid[:20]}...")

    token = get_access_token()
    if not token:
        print("✗ 인증 실패")
        return False
    print("✓ 인증 성공")

    sheets = get_sheet_names(sid, token)
    if sheets:
        print(f"✓ 시트 목록: {sheets}")
    else:
        print("✗ 시트 조회 실패 — 서비스 계정에 편집 권한이 있는지 확인")
        return False

    print("=" * 50)
    print("테스트 완료")
    return True


# ============================================================
# CLI
# ============================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Re:NK Google Sheets 아카이빙')
    parser.add_argument('--test', action='store_true', help='API 연결 테스트')
    parser.add_argument('--init', action='store_true', help='시트 + 헤더 자동 생성')
    args = parser.parse_args()

    if args.test:
        test_connection()
    elif args.init:
        initialize_sheets()
    else:
        print("사용법:")
        print("  python google_sheets_writer.py --test   # 연결 테스트")
        print("  python google_sheets_writer.py --init   # 시트 초기화")
