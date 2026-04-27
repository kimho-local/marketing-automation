#!/usr/bin/env python3
"""
Re:NK 네이버 스마트스토어 커머스 API 수집기
=============================================
주문/결제 데이터 자동 수집 → 카페24 커머스와 동일 구조

수집 항목:
  - 결제금액(순매출), 환불금액, 주문건수, 결제자수(유니크)
  - 객단가(=결제금액/결제자수), 상품별 판매 TOP 3

사용법:
  python smartstore_api_fetcher.py --test
  python smartstore_api_fetcher.py --date 2026-04-26
  python smartstore_api_fetcher.py --since 2026-04-20 --until 2026-04-26
"""

import os
import sys
import json
import time
import base64
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from collections import defaultdict

try:
    import bcrypt
except ImportError:
    print("[ERROR] bcrypt 패키지 필요: pip install bcrypt")
    sys.exit(1)


# ============================================================
# 설정
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(SCRIPT_DIR, 'config', 'renk_smartstore_credentials.json')
DATA_DIR = os.path.join(SCRIPT_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

API_BASE = 'https://api.commerce.naver.com/external'

# 주문 상태 (결제 완료 기준)
PAID_STATUSES = [
    'PAYED',           # 결제 완료
    'DELIVERING',      # 배송 중
    'DELIVERED',       # 배송 완료
    'PURCHASE_DECIDED', # 구매 확정
    'EXCHANGED',       # 교환 완료
    'CANCELED',        # 취소 (환불 계산용)
    'RETURNED',        # 반품 완료 (환불 계산용)
]

REFUND_STATUSES = ['CANCELED', 'RETURNED']


# ============================================================
# 인증 — 토큰 자동 갱신 매니저
# ============================================================

class TokenManager:
    """
    네이버 커머스 API 토큰 매니저
    - 최초 발급 후 메모리 캐싱
    - 만료 5분 전 자동 갱신
    - API 호출 시 401 응답 → 즉시 재발급 후 재시도
    """

    def __init__(self, creds: dict = None):
        self._creds = creds
        self._token = ''
        self._expires_at = 0  # unix timestamp

    def load_credentials(self) -> dict:
        """인증 파일 로드 (없으면 기본값 사용)"""
        if self._creds:
            return self._creds
        if os.path.exists(CREDS_FILE):
            with open(CREDS_FILE, 'r', encoding='utf-8') as f:
                self._creds = json.load(f)
        else:
            self._creds = {
                'client_id': '7X8N8LqGhpKmGhuaFLOLGp',
                'client_secret': '$2a$04$css.F0Qf/qKZIXI8xMty3O',
            }
        return self._creds

    @staticmethod
    def _generate_signature(client_id: str, client_secret: str, timestamp: int) -> str:
        """
        전자서명 생성 (공식 문서 기준)
        bcrypt.hashpw(client_id_timestamp, client_secret) → Base64
        """
        password = f"{client_id}_{timestamp}".encode('utf-8')
        salt = client_secret.encode('utf-8')
        hashed = bcrypt.hashpw(password, salt)
        return base64.b64encode(hashed).decode('utf-8')

    def get_token(self, force: bool = False) -> str:
        """
        유효한 토큰 반환.
        - 캐시에 유효 토큰이 있으면 그대로 반환
        - 만료 5분 전이거나 force=True면 재발급
        """
        if not force and self._token:
            if time.time() < self._expires_at - 300:
                return self._token

        creds = self.load_credentials()
        client_id = creds['client_id']
        client_secret = creds['client_secret']
        timestamp = int(time.time() * 1000)

        signature = self._generate_signature(client_id, client_secret, timestamp)

        url = f"{API_BASE}/v1/oauth2/token"
        data = urllib.parse.urlencode({
            'client_id': client_id,
            'timestamp': timestamp,
            'client_secret_sign': signature,
            'grant_type': 'client_credentials',
            'type': 'SELF',
        }).encode('utf-8')

        req = urllib.request.Request(
            url, data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                token = result.get('access_token', '')
                expires_in = result.get('expires_in', 7200)
                if token:
                    self._token = token
                    self._expires_at = time.time() + expires_in
                    label = '갱신' if not force else '재발급'
                    print(f"  [AUTH] 토큰 {label} 성공 (유효: {expires_in // 3600}시간)")
                return token
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            print(f"[ERROR] 토큰 발급 실패 (HTTP {e.code}): {body[:300]}")
            return ''
        except Exception as e:
            print(f"[ERROR] 토큰 발급 실패: {e}")
            return ''

    def invalidate(self):
        """현재 토큰 무효화 → 다음 get_token() 호출 시 재발급"""
        self._token = ''
        self._expires_at = 0


# 모듈 전역 토큰 매니저
_tm = TokenManager()


def load_credentials() -> dict:
    """하위 호환용 래퍼"""
    return _tm.load_credentials()


def get_access_token(creds: dict = None) -> str:
    """하위 호환용 래퍼"""
    if creds and not _tm._creds:
        _tm._creds = creds
    return _tm.get_token()


# ============================================================
# API 호출 공통 (401 → 토큰 자동 갱신 + 재시도)
# ============================================================

def api_get(token: str, endpoint: str, params: dict = None, retry: int = 3) -> dict:
    """커머스 API GET 요청 (401 → 토큰 갱신, 429 → 대기 재시도)"""
    url = f"{API_BASE}{endpoint}"
    if params:
        url += '?' + urllib.parse.urlencode(params, doseq=True, quote_via=urllib.parse.quote)

    current_token = token
    for attempt in range(retry):
        req = urllib.request.Request(
            url,
            headers={
                'Authorization': f'Bearer {current_token}',
                'Content-Type': 'application/json',
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            if e.code == 401 and attempt < retry - 1:
                print(f"  [401] 토큰 만료 → 자동 갱신 중...")
                _tm.invalidate()
                new_token = _tm.get_token(force=True)
                if new_token:
                    current_token = new_token
                    continue
            if e.code == 429 and attempt < retry - 1:
                wait = 2 * (attempt + 1)
                print(f"  [429] Rate limit → {wait}초 대기...")
                time.sleep(wait)
                continue
            print(f"[ERROR] API ({endpoint}, HTTP {e.code}): {body[:300]}")
            return {}
        except Exception as e:
            print(f"[ERROR] API ({endpoint}): {e}")
            return {}

    return {}


def api_post(token: str, endpoint: str, body: dict, retry: int = 3) -> dict:
    """커머스 API POST 요청 (401 → 토큰 갱신, 429 → 대기 재시도)"""
    url = f"{API_BASE}{endpoint}"
    data = json.dumps(body).encode('utf-8')

    current_token = token
    for attempt in range(retry):
        req = urllib.request.Request(
            url, data=data,
            headers={
                'Authorization': f'Bearer {current_token}',
                'Content-Type': 'application/json',
            },
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body_text = e.read().decode('utf-8', errors='replace')
            if e.code == 401 and attempt < retry - 1:
                print(f"  [401] 토큰 만료 → 자동 갱신 중...")
                _tm.invalidate()
                new_token = _tm.get_token(force=True)
                if new_token:
                    current_token = new_token
                    continue
            if e.code == 429 and attempt < retry - 1:
                wait = 2 * (attempt + 1)
                print(f"  [429] Rate limit → {wait}초 대기...")
                time.sleep(wait)
                continue
            print(f"[ERROR] API POST ({endpoint}, HTTP {e.code}): {body_text[:300]}")
            return {}
        except Exception as e:
            print(f"[ERROR] API POST ({endpoint}): {e}")
            return {}

    return {}


# ============================================================
# 주문 데이터 수집
# ============================================================

def _collect_order_ids(token: str, date_str: str,
                       changed_type: str = None) -> list:
    """
    lastChangedStatuses로 특정 날짜의 상품주문번호(str) 목록 수집.
    changed_type: 'PAYED' 등 지정 시 해당 상태 변경 건만 조회.
    """
    start_dt = f"{date_str}T00:00:00.000+09:00"
    end_dt = f"{date_str}T23:59:59.999+09:00"

    all_ids = []
    params = {
        'lastChangedFrom': start_dt,
        'lastChangedTo': end_dt,
    }
    if changed_type:
        params['lastChangedType'] = changed_type

    max_pages = 50
    for _ in range(max_pages):
        result = api_get(token, '/v1/pay-order/seller/product-orders/last-changed-statuses', params)
        if not result:
            break

        data = result.get('data', result)
        if isinstance(data, dict):
            statuses = data.get('lastChangeStatuses', [])
        elif isinstance(data, list):
            statuses = data
        else:
            break

        if not statuses:
            break

        for item in statuses:
            if isinstance(item, str):
                all_ids.append(item)
            elif isinstance(item, dict):
                pid = item.get('productOrderId', '')
                if pid:
                    all_ids.append(pid)

        # 페이지네이션
        more = (data if isinstance(data, dict) else result).get('more', {})
        if isinstance(more, dict) and more.get('moreSequence'):
            params['lastChangedFrom'] = more['moreSequence']
        else:
            break

    return all_ids


def _fetch_order_details(token: str, order_ids: list) -> list:
    """상품주문번호 목록 → 상세 조회 (300건씩 분할)"""
    if not order_ids:
        return []

    all_details = []
    for i in range(0, len(order_ids), 300):
        chunk = order_ids[i:i + 300]
        result = api_post(token, '/v1/pay-order/seller/product-orders/query', {
            'productOrderIds': chunk,
        })
        if result:
            detail_data = result.get('data', [])
            all_details.extend(detail_data)
        if i + 300 < len(order_ids):
            time.sleep(0.5)

    return all_details


def fetch_orders_for_date(token: str, date_str: str) -> dict:
    """
    특정 날짜의 주문 상세 수집 (T-1 최적화)

    반환: {
        'payed_orders': [...],   # PAYED 쿼리 → 결제 집계용
        'refund_orders': [...],  # ALL 쿼리 중 CANCELED/RETURNED → 환불 집계용
    }

    전략:
    1) PAYED 쿼리 → 해당 날짜에 결제 완료된 건 (결제 집계용)
    2) ALL 쿼리 → 전체 상태 변경 건 중 CANCELED/RETURNED만 추출 (환불용)
    """
    REFUND_STATUSES_SET = {'CANCELED', 'RETURNED'}

    # 1단계: PAYED 상태 변경 건 (결제 완료)
    payed_ids = _collect_order_ids(token, date_str, changed_type='PAYED')
    payed_id_set = set(payed_ids)

    # 2단계: 전체 상태 변경 건 (환불 포착)
    all_change_ids = _collect_order_ids(token, date_str, changed_type=None)
    # PAYED에 없는 ID만 → 상세 조회 후 환불 건 필터
    refund_candidate_ids = [x for x in all_change_ids if x not in payed_id_set]

    result = {'payed_orders': [], 'refund_orders': []}

    # PAYED 건 상세 조회
    if payed_ids:
        result['payed_orders'] = _fetch_order_details(token, list(dict.fromkeys(payed_ids)))

    # 환불 후보 상세 조회 → CANCELED/RETURNED만 남기기
    if refund_candidate_ids:
        candidates = _fetch_order_details(token, list(dict.fromkeys(refund_candidate_ids)))
        for order in candidates:
            po = order.get('productOrder', order)
            if isinstance(po, dict):
                status = po.get('productOrderStatus', '')
                if status in REFUND_STATUSES_SET:
                    result['refund_orders'].append(order)

    return result


def aggregate_daily(order_data: dict, date_str: str) -> dict:
    """
    주문 목록 → 일별 집계
    반환: {
        'paid_amount': 총결제금액,
        'refund_amount': 총환불금액,
        'net_revenue': 순매출,
        'order_count': 주문건수,
        'unique_customers': 결제자수,
        'avg_order_value': 객단가,
        'product_sales': {상품명: {amount, quantity, count}},
    }
    """
    payed_orders = order_data.get('payed_orders', [])
    refund_orders = order_data.get('refund_orders', [])

    paid_total = 0
    refund_total = 0
    shipping_total = 0
    package_ids_paid = set()
    buyer_keys = set()
    refund_count = 0
    product_map = defaultdict(lambda: {'amount': 0, 'quantity': 0, 'count': 0})

    def _extract(po):
        """productOrder dict 추출"""
        if isinstance(po, dict):
            return po.get('productOrder', po)
        return {}

    def _buyer_key(po):
        """수령인 기반 구매자 키"""
        addr = po.get('shippingAddress', {})
        if isinstance(addr, dict):
            name = addr.get('name', '')
            tel = addr.get('tel1', addr.get('tel', ''))
            if name or tel:
                return f"{name}|{tel}"
        return po.get('packageNumber', po.get('productOrderId', ''))

    # ── 결제 건 집계 (PAYED 쿼리 결과만 사용) ──
    for order in payed_orders:
        po = _extract(order)
        if not isinstance(po, dict):
            continue

        total_price = int(po.get('totalPaymentAmount', 0) or 0)
        shipping = int(po.get('deliveryFeeAmount', 0) or 0)
        pkg = po.get('packageNumber', '') or po.get('productOrderId', '')

        paid_total += total_price
        shipping_total += shipping
        package_ids_paid.add(pkg)

        bk = _buyer_key(po)
        if bk:
            buyer_keys.add(bk)

        # 상품별 집계
        product_name = po.get('productName', '기타')
        quantity = int(po.get('quantity', 1) or 1)
        product_map[product_name]['amount'] += abs(total_price)
        product_map[product_name]['quantity'] += quantity
        product_map[product_name]['count'] += 1

    # ── 환불 건 집계 (ALL 쿼리 → CANCELED/RETURNED만) ──
    for order in refund_orders:
        po = _extract(order)
        if not isinstance(po, dict):
            continue
        total_price = int(po.get('totalPaymentAmount', 0) or 0)
        refund_total += abs(total_price)
        refund_count += 1

    # 주문건수: unique packageNumber
    order_count = len(package_ids_paid)
    # 결제자수: unique 수령인
    unique_customers = len(buyer_keys) if buyer_keys else order_count
    net_revenue = paid_total - refund_total
    avg_order_value = round(paid_total / unique_customers) if unique_customers > 0 else 0

    # 디버그 요약
    total_items = len(payed_orders)
    print(f"    [집계] 결제: {paid_total:,}원(상품 {total_items}건, 주문 {order_count}건, "
          f"결제자 {unique_customers}명) | "
          f"환불: {refund_total:,}원({refund_count}건) | "
          f"배송비: {shipping_total:,}원")

    # 상품 TOP 정렬 (금액 기준)
    top_products = sorted(
        [{'name': k, **v} for k, v in product_map.items()],
        key=lambda x: x['amount'],
        reverse=True,
    )

    return {
        'paid_amount': paid_total,
        'refund_amount': refund_total,
        'net_revenue': net_revenue,
        'order_count': order_count,
        'unique_customers': unique_customers,
        'avg_order_value': avg_order_value,
        'product_sales': top_products[:10],  # TOP 10
    }


# ============================================================
# 메인 수집 함수
# ============================================================

def fetch_smartstore_data(since: str, until: str) -> dict:
    """
    날짜 범위의 스마트스토어 커머스 데이터 수집

    반환: {
        '2026-04-26': {
            'paid_amount': ...,
            'refund_amount': ...,
            'net_revenue': ...,
            'order_count': ...,
            'unique_customers': ...,
            'avg_order_value': ...,
            'product_sales': [...],
        },
        ...
    }
    """
    print(f"\n{'='*50}")
    print(f"스마트스토어 커머스 데이터 수집: {since} ~ {until}")
    print(f"{'='*50}")

    creds = load_credentials()
    token = get_access_token(creds)
    if not token:
        print("[ERROR] 인증 실패 — 토큰 발급 불가")
        return {}

    results = {}
    current = datetime.strptime(since, '%Y-%m-%d')
    end = datetime.strptime(until, '%Y-%m-%d')

    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        print(f"\n  [{date_str}] 주문 수집 중...", end='', flush=True)

        # 주문 조회: {payed_orders: [...], refund_orders: [...]}
        order_data = fetch_orders_for_date(token, date_str)

        payed_cnt = len(order_data.get('payed_orders', []))
        refund_cnt = len(order_data.get('refund_orders', []))
        print(f" 결제 {payed_cnt}건 + 환불 {refund_cnt}건")

        if payed_cnt > 0 or refund_cnt > 0:
            daily = aggregate_daily(order_data, date_str)
            results[date_str] = daily
            print(f"  → 결제 {daily['paid_amount']:,}원 | "
                  f"환불 {daily['refund_amount']:,}원 | "
                  f"주문 {daily['order_count']}건 | "
                  f"구매자 {daily['unique_customers']}명")
        else:
            results[date_str] = {
                'paid_amount': 0, 'refund_amount': 0, 'net_revenue': 0,
                'order_count': 0, 'unique_customers': 0, 'avg_order_value': 0,
                'product_sales': [],
            }
            print("  → 데이터 없음")

        current += timedelta(days=1)

    # CSV 저장
    _save_csv(results)
    print(f"\n수집 완료: {len(results)}일")

    return results


def _save_csv(results: dict):
    """일별 데이터 CSV 저장"""
    csv_path = os.path.join(DATA_DIR, 'smartstore_commerce_daily.csv')
    exists = os.path.exists(csv_path)

    header = '날짜,결제금액,환불금액,순매출,주문건수,결제자수,객단가\n'
    lines = []
    for date_str in sorted(results.keys()):
        d = results[date_str]
        lines.append(
            f"{date_str},{d['paid_amount']},{d['refund_amount']},{d['net_revenue']},"
            f"{d['order_count']},{d['unique_customers']},{d['avg_order_value']}\n"
        )

    mode = 'a' if exists else 'w'
    with open(csv_path, mode, encoding='utf-8') as f:
        if not exists:
            f.write(header)
        f.writelines(lines)


# ============================================================
# 연결 테스트
# ============================================================

def test_connection():
    """API 연결 테스트"""
    print("=" * 50)
    print("네이버 스마트스토어 커머스 API 연결 테스트")
    print("=" * 50)

    creds = load_credentials()
    print(f"  Client ID: {creds['client_id'][:10]}...")

    token = get_access_token(creds)
    if token:
        print(f"  ✓ Access Token 발급 성공")
        print(f"    Token: {token[:20]}...")

        # 어제 주문 조회 테스트
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        print(f"  → 어제({yesterday}) 주문 수집 시도...")
        order_data = fetch_orders_for_date(token, yesterday)
        payed = len(order_data.get('payed_orders', []))
        refunds = len(order_data.get('refund_orders', []))
        print(f"  ✓ 결제 {payed}건 + 환불 {refunds}건 조회됨")
    else:
        print("  ✗ 인증 실패")
        print("    config/renk_smartstore_credentials.json 확인 필요")

    print("=" * 50)
    return bool(token)


# ============================================================
# CLI
# ============================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Re:NK 스마트스토어 커머스 수집기')
    parser.add_argument('--date', help='수집 날짜 (YYYY-MM-DD)')
    parser.add_argument('--since', help='시작일')
    parser.add_argument('--until', help='종료일')
    parser.add_argument('--test', action='store_true', help='연결 테스트')
    args = parser.parse_args()

    if args.test:
        test_connection()
    elif args.date:
        data = fetch_smartstore_data(args.date, args.date)
        if data:
            print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.since and args.until:
        data = fetch_smartstore_data(args.since, args.until)
        if data:
            print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        # 기본: 어제 데이터
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        data = fetch_smartstore_data(yesterday, yesterday)
        if data:
            print(json.dumps(data, ensure_ascii=False, indent=2))
