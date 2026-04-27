#!/usr/bin/env python3
"""
Re:NK 카페24 API 데이터 자동 수집기
=====================================
/admin/dashboard API 기반 → 대시보드와 100% 일치하는 수치 수집
토큰 만료 시 자동 갱신 (refresh_token)

사용법:
  python cafe24_api_fetcher.py                       # 어제 데이터 수집
  python cafe24_api_fetcher.py --date 2026-03-30     # 특정 날짜
  python cafe24_api_fetcher.py --since 2026-03-01 --until 2026-03-30  # 범위
  python cafe24_api_fetcher.py --test                # API 연결 테스트
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
import base64
from datetime import datetime, timedelta


# ============================================================
# 설정값
# ============================================================

CONFIG = {
    'CLIENT_ID': 'LzxcZZ7HMFEnzlltfgvgOE',
    'CLIENT_SECRET': '38aX5qPICVzrdlreBRwaqE',
    'MALL_ID': 'renk0',
    'REDIRECT_URI': 'https://www.re-nk.co.kr',
    'API_BASE': 'https://renk0.cafe24api.com/api/v2',
    'TOKEN_URL': 'https://renk0.cafe24api.com/api/v2/oauth/token',
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, 'config', 'renk_cafe24_token.json')


# ============================================================
# 토큰 관리
# ============================================================

def load_token() -> dict:
    """저장된 토큰 파일 읽기"""
    if not os.path.exists(TOKEN_FILE):
        print("[ERROR] cafe24_token.json 파일 없음. 먼저 cafe24_get_token.py 실행 필요.")
        return {}
    with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_token(token_data: dict):
    """토큰 파일 저장"""
    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(token_data, f, indent=2, ensure_ascii=False)


def is_token_expired(token_data: dict) -> bool:
    """Access Token 만료 여부 확인"""
    expires_at = token_data.get('expires_at', '')
    if not expires_at:
        return True
    try:
        exp = datetime.strptime(expires_at[:19], '%Y-%m-%dT%H:%M:%S')
        return datetime.now() >= exp
    except ValueError:
        return True


def refresh_access_token(token_data: dict) -> dict:
    """Refresh Token으로 Access Token 자동 갱신"""
    rt = token_data.get('refresh_token', '')
    if not rt:
        print("[ERROR] Refresh Token 없음. cafe24_get_token.py로 재발급 필요.")
        return {}

    credentials = base64.b64encode(
        f"{CONFIG['CLIENT_ID']}:{CONFIG['CLIENT_SECRET']}".encode()
    ).decode()

    data = urllib.parse.urlencode({
        'grant_type': 'refresh_token',
        'refresh_token': rt,
    }).encode()

    req = urllib.request.Request(
        CONFIG['TOKEN_URL'],
        data=data,
        headers={
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            save_token(result)
            print(f"[INFO] 카페24 토큰 자동 갱신 완료 (만료: {result.get('expires_at', '?')})")
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f"[ERROR] 토큰 갱신 실패 (HTTP {e.code}): {body}")
        return {}


def get_valid_token() -> str:
    """유효한 Access Token 반환 (만료 시 자동 갱신)"""
    token_data = load_token()
    if not token_data:
        return ''

    if is_token_expired(token_data):
        print("[INFO] Access Token 만료 → 자동 갱신 시도...")
        token_data = refresh_access_token(token_data)
        if not token_data:
            return ''

    return token_data.get('access_token', '')


# ============================================================
# API 호출
# ============================================================

def api_get(endpoint: str, params: dict = None, retry: int = 3) -> dict:
    """카페24 REST API GET 요청 (429 Rate Limit 자동 재시도)"""
    import time as _time

    token = get_valid_token()
    if not token:
        return {}

    url = f"{CONFIG['API_BASE']}{endpoint}"
    if params:
        url += '?' + urllib.parse.urlencode(params)

    for attempt in range(retry):
        req = urllib.request.Request(
            url,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'X-Cafe24-Api-Version': '2026-03-01',
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            if e.code == 429:
                wait = 2 * (attempt + 1)
                if attempt < retry - 1:
                    print(f"  [429] Rate limit → {wait}초 대기 후 재시도...")
                    _time.sleep(wait)
                    continue
            print(f"[ERROR] API 호출 실패 ({endpoint}, HTTP {e.code}): {body}")
            return {}
        except Exception as e:
            print(f"[ERROR] API 호출 예외 ({endpoint}): {e}")
            return {}

    return {}


def _parse_money(val) -> float:
    """금액 문자열/숫자 → float 변환"""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.replace(',', '').strip()
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


# ============================================================
# Dashboard API 기반 매출 데이터 수집 (대시보드 100% 일치)
# ============================================================

def fetch_dashboard(start_date: str, end_date: str) -> list:
    """
    /admin/dashboard API 호출 → daily_sales_stats 반환

    반환: [
        {
            'date': '2026-04-21',
            'paid_price': '5040000.00',
            'refund_price': '467000.00',
            'order_price': '24011800.00',
            'order_count': 105,
            ...
        }, ...
    ]
    """
    result = api_get('/admin/dashboard', {
        'start_date': start_date,
        'end_date': end_date,
    })
    if not result:
        return []

    dashboard = result.get('dashboard', {})
    return dashboard.get('daily_sales_stats', [])


def _parse_dashboard_day(day: dict) -> dict:
    """
    dashboard daily_sales_stats 한 건 → 통합 데이터 dict 변환

    대시보드 필드 매핑:
        paid_price       → 결제합계
        refund_price     → 환불합계
        order_price      → 상품구매금액
        order_count      → 주문건수
        payed_count      → 결제완료건수
        refund_count     → 환불건수
        canceled_count   → 취소건수
    """
    paid   = int(_parse_money(day.get('paid_price', 0)))
    refund = int(_parse_money(day.get('refund_price', 0)))
    net    = paid - refund
    order_count = int(day.get('order_count', 0))

    return {
        'date': day.get('date', ''),
        'paid_amount': paid,                # 결제합계
        'refund_amount': refund,            # 환불합계
        'net_sales': net,                   # 순매출
        'order_count': order_count,         # 주문건수
        'unique_customers': 0,              # Dashboard에서 미제공 → 주문 API 보완
        'avg_order_value': int(net / order_count) if order_count > 0 else 0,
        'product_amount': int(_parse_money(day.get('order_price', 0))),
        'discount_amount': 0,               # 개별 산출 불가
        'coupon_amount': 0,                  # 개별 산출 불가
        'shipping_fee': 0,                   # 개별 산출 불가
        'payed_count': int(day.get('payed_count', 0)),
        'refund_count': int(day.get('refund_count', 0)),
        'canceled_count': int(day.get('canceled_count', 0)),
    }


def _count_unique_customers(date_str: str) -> int:
    """
    주문 리스트 API에서 구매자 수(중복제거) 집계
    Dashboard API에서 제공하지 않는 유일한 지표
    → billing_name 기반 (모든 주문에 존재, 대시보드와 가장 근접)
    → 상세 조회 없이 리스트 API만 사용 (Rate Limit 최소화)
    """
    start = f"{date_str}T00:00:00+09:00"
    end   = f"{date_str}T23:59:59+09:00"

    customer_ids = set()
    offset = 0
    limit = 100

    while True:
        result = api_get('/admin/orders', {
            'start_date': start,
            'end_date': end,
            'limit': limit,
            'offset': offset,
        })
        orders = result.get('orders', [])
        if not orders:
            break

        for o in orders:
            # billing_name: 모든 주문(회원+비회원)에 존재, 대시보드 구매자수와 가장 근접
            buyer = (o.get('billing_name') or o.get('member_id') or '')
            if buyer:
                customer_ids.add(buyer)

        if len(orders) < limit:
            break
        offset += limit

    return len(customer_ids)


def _count_first_repeat(date_str: str) -> dict:
    """
    당일 주문의 첫구매/재구매 구분
    - member_id가 있는 주문: 해당 회원의 이전 주문 이력 조회 → 있으면 재구매, 없으면 첫구매
    - member_id가 없는 주문(비회원): 첫구매로 간주

    반환: {
        'first_buyers': 5,       ← 첫구매 고객 수
        'repeat_buyers': 3,      ← 재구매 고객 수
        'total_buyers': 8,       ← 총 구매 고객 수
        'first_ratio': 62.5,     ← 첫구매 비율(%)
        'repeat_ratio': 37.5,    ← 재구매 비율(%)
    }
    """
    import time as _time

    start = f"{date_str}T00:00:00+09:00"
    end   = f"{date_str}T23:59:59+09:00"

    # 1) 당일 주문 전체 수집
    all_orders = []
    offset = 0
    limit = 100

    while True:
        result = api_get('/admin/orders', {
            'start_date': start,
            'end_date': end,
            'limit': limit,
            'offset': offset,
        })
        orders = result.get('orders', [])
        if not orders:
            break
        all_orders.extend(orders)
        if len(orders) < limit:
            break
        offset += limit

    if not all_orders:
        return {
            'first_buyers': 0, 'repeat_buyers': 0, 'total_buyers': 0,
            'first_ratio': 0.0, 'repeat_ratio': 0.0,
        }

    # 2) 고유 구매자 분류 (member_id 기준)
    member_ids = set()
    non_member_count = 0
    buyer_names = set()

    for o in all_orders:
        mid = o.get('member_id', '')
        buyer = o.get('billing_name') or mid or ''
        if not buyer or buyer in buyer_names:
            continue
        buyer_names.add(buyer)

        if mid:
            member_ids.add(mid)
        else:
            non_member_count += 1

    # 3) 회원별 이전 주문 이력 확인
    #    당일 이전(end_date < 오늘) 주문이 있으면 재구매
    #    ※ 카페24 API 제약: start_date~end_date 범위 최대 6개월
    #      → 6개월 이내 주문 이력 기준으로 재구매 판별
    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    yesterday = (target_date - timedelta(days=1)).strftime('%Y-%m-%d')
    prev_start = '2026-02-19T00:00:00+09:00'
    prev_end = f"{yesterday}T23:59:59+09:00"

    first_members = 0
    repeat_members = 0

    for mid in member_ids:
        result = api_get('/admin/orders/count', {
            'member_id': mid,
            'start_date': prev_start,
            'end_date': prev_end,
        })
        prev_count = result.get('count', 0)

        if prev_count > 0:
            repeat_members += 1
        else:
            first_members += 1
        _time.sleep(0.3)  # Rate Limit 방지

    # 4) 집계
    first_total = first_members + non_member_count  # 비회원 = 첫구매
    repeat_total = repeat_members
    total = first_total + repeat_total

    return {
        'first_buyers': first_total,
        'repeat_buyers': repeat_total,
        'total_buyers': total,
        'first_ratio': round(first_total / total * 100, 1) if total > 0 else 0.0,
        'repeat_ratio': round(repeat_total / total * 100, 1) if total > 0 else 0.0,
    }


# ============================================================
# 일별 데이터 수집 메인
# ============================================================

def _fetch_from_orders(date_str: str) -> dict:
    """
    주문 API 기반 일별 데이터 집계 (Dashboard API fallback)
    Dashboard는 오늘/어제만 반환 → 그 이전 날짜는 주문 API로 직접 집계
    """
    print(f"  [INFO] 주문 API로 {date_str} 데이터 집계 중...")
    start = f"{date_str}T00:00:00+09:00"
    end   = f"{date_str}T23:59:59+09:00"

    all_orders = []
    offset = 0
    limit = 100

    while True:
        result = api_get('/admin/orders', {
            'start_date': start,
            'end_date': end,
            'limit': limit,
            'offset': offset,
        })
        orders = result.get('orders', [])
        if not orders:
            break
        all_orders.extend(orders)
        if len(orders) < limit:
            break
        offset += limit

    if not all_orders:
        return {
            'date': date_str,
            'paid_amount': 0, 'refund_amount': 0, 'net_sales': 0,
            'order_count': 0, 'unique_customers': 0, 'avg_order_value': 0,
            'product_amount': 0, 'discount_amount': 0,
            'coupon_amount': 0, 'shipping_fee': 0,
        }

    paid_total = 0
    refund_total = 0
    product_total = 0
    customer_ids = set()

    for o in all_orders:
        payment = _parse_money(o.get('payment_amount', 0))
        paid_total += int(payment)

        # 환불 금액
        refund = _parse_money(o.get('refund_amount', 0))
        refund_total += int(refund)

        # 상품금액
        product = _parse_money(o.get('total_product_amount') or o.get('order_price_amount', 0))
        product_total += int(product)

        # 구매자 (중복제거)
        buyer = o.get('billing_name') or o.get('member_id') or ''
        if buyer:
            customer_ids.add(buyer)

    order_count = len(all_orders)
    net = paid_total - refund_total
    avg = int(net / order_count) if order_count > 0 else 0

    return {
        'date': date_str,
        'paid_amount': paid_total,
        'refund_amount': refund_total,
        'net_sales': net,
        'order_count': order_count,
        'unique_customers': len(customer_ids),
        'avg_order_value': avg,
        'product_amount': product_total,
        'discount_amount': 0,
        'coupon_amount': 0,
        'shipping_fee': 0,
    }


def fetch_daily_data(date_str: str) -> dict:
    """
    특정 날짜의 카페24 자사몰 데이터 수집
    1차: /admin/dashboard API (오늘/어제만 가능 — 대시보드 100% 일치)
    2차: Dashboard에 없으면 /admin/orders API로 직접 집계

    반환: {
        'date': '2026-04-21',
        'paid_amount': 5040000,      ← 결제합계
        'refund_amount': 467000,     ← 환불합계
        'net_sales': 4573000,        ← 순매출
        'order_count': 105,
        'unique_customers': 95,
        'avg_order_value': 48136,
        'product_amount': 24011800,
        ...
    }
    """
    print(f"[INFO] 카페24 데이터 수집 중: {date_str}")

    # 1) Dashboard API 시도 (오늘/어제만 반환됨)
    stats = fetch_dashboard(date_str, date_str)
    day = None
    for s in stats:
        if s.get('date') == date_str:
            day = s
            break

    if day:
        print(f"  (Dashboard API)")
        summary = _parse_dashboard_day(day)
        # 구매자수 보완 (주문 리스트 API)
        if summary['order_count'] > 0:
            print(f"  구매자수 집계 중...")
            summary['unique_customers'] = _count_unique_customers(date_str)
    else:
        # 2) Fallback: 주문 API로 직접 집계
        summary = _fetch_from_orders(date_str)

    # 첫구매/재구매 집계
    if summary['order_count'] > 0:
        print(f"  첫구매/재구매 판별 중...")
        fr = _count_first_repeat(date_str)
        summary['first_buyers'] = fr['first_buyers']
        summary['repeat_buyers'] = fr['repeat_buyers']
        summary['first_ratio'] = fr['first_ratio']
        summary['repeat_ratio'] = fr['repeat_ratio']

        print(f"  결제합계 {summary['paid_amount']:,}원 | "
              f"환불 {summary['refund_amount']:,}원 | "
              f"순매출 {summary['net_sales']:,}원 | "
              f"주문 {summary['order_count']}건 | "
              f"구매자 {summary['unique_customers']}명 | "
              f"객단가 {summary['avg_order_value']:,}원")
        print(f"  첫구매 {fr['first_buyers']}명({fr['first_ratio']}%) | "
              f"재구매 {fr['repeat_buyers']}명({fr['repeat_ratio']}%)")
    else:
        summary['first_buyers'] = 0
        summary['repeat_buyers'] = 0
        summary['first_ratio'] = 0.0
        summary['repeat_ratio'] = 0.0
        print(f"  {date_str} 주문 없음 (0건)")

    return summary


def fetch_range(since: str, until: str) -> dict:
    """
    날짜 범위 수집 (Dashboard API 기반)
    Dashboard API가 범위를 지원하면 한 번에, 아니면 일별 호출

    반환: { '2026-03-29': {...}, '2026-03-30': {...}, ... }
    """
    import time as _time

    print(f"[INFO] 카페24 범위 수집: {since} ~ {until}")

    # Dashboard API 범위 호출 시도
    stats = fetch_dashboard(since, until)

    # 응답에서 날짜별 매핑
    dashboard_map = {}
    for s in stats:
        d = s.get('date', '')
        if d:
            dashboard_map[d] = s

    # 전체 날짜 생성
    results = {}
    current = datetime.strptime(since, '%Y-%m-%d')
    end = datetime.strptime(until, '%Y-%m-%d')

    while current <= end:
        date_str = current.strftime('%Y-%m-%d')

        if date_str in dashboard_map:
            # Dashboard 응답에 포함된 날짜
            summary = _parse_dashboard_day(dashboard_map[date_str])
            if summary['order_count'] > 0:
                summary['unique_customers'] = _count_unique_customers(date_str)
                _time.sleep(0.5)
            results[date_str] = summary
            print(f"  {date_str}: 결제 {summary['paid_amount']:,}원 | "
                  f"환불 {summary['refund_amount']:,}원 | "
                  f"순매출 {summary['net_sales']:,}원 | "
                  f"주문 {summary['order_count']}건")
        else:
            # Dashboard 범위 밖 → 개별 호출
            day_stats = fetch_dashboard(date_str, date_str)
            day = None
            for s in day_stats:
                if s.get('date') == date_str:
                    day = s
                    break

            if day:
                summary = _parse_dashboard_day(day)
                if summary['order_count'] > 0:
                    summary['unique_customers'] = _count_unique_customers(date_str)
                    _time.sleep(0.5)
                results[date_str] = summary
                print(f"  {date_str}: 결제 {summary['paid_amount']:,}원 | "
                      f"환불 {summary['refund_amount']:,}원 | "
                      f"순매출 {summary['net_sales']:,}원 | "
                      f"주문 {summary['order_count']}건")
            else:
                # 데이터 없는 날짜 → 0으로 채움
                results[date_str] = {
                    'date': date_str,
                    'paid_amount': 0, 'refund_amount': 0, 'net_sales': 0,
                    'order_count': 0, 'unique_customers': 0, 'avg_order_value': 0,
                    'product_amount': 0, 'discount_amount': 0,
                    'coupon_amount': 0, 'shipping_fee': 0,
                }
                print(f"  {date_str}: 데이터 없음")

            _time.sleep(0.5)

        current += timedelta(days=1)

    return results


# ============================================================
# 상품 목록 (월보고서용)
# ============================================================

def fetch_products(limit: int = 20) -> list:
    """상품 목록 조회"""
    result = api_get('/admin/products', {
        'limit': limit,
        'fields': 'product_no,product_name,price,retail_price,supply_price,selling,display',
    })
    return result.get('products', [])


# ============================================================
# API 연결 테스트
# ============================================================

def test_connection():
    """카페24 API 연결 테스트 (Dashboard API 기반)"""
    print("=" * 50)
    print("카페24 API 연결 테스트")
    print("=" * 50)

    # 1. 토큰 확인
    token_data = load_token()
    if not token_data:
        print("✗ 토큰 파일 없음")
        return False

    print(f"✓ 토큰 파일 존재")
    print(f"  Access Token: {token_data.get('access_token', '')[:20]}...")
    print(f"  만료: {token_data.get('expires_at', '?')}")
    print(f"  Scopes: {token_data.get('scopes', [])}")

    # 2. 토큰 유효성
    if is_token_expired(token_data):
        print("⚠ 토큰 만료 → 갱신 시도...")
        token_data = refresh_access_token(token_data)
        if not token_data:
            print("✗ 갱신 실패")
            return False
        print("✓ 갱신 성공")

    # 3. 스토어 정보 조회
    store = api_get('/admin/store')
    if store:
        shop = store.get('store', {})
        print(f"✓ 스토어 연결 확인: {shop.get('shop_name', '?')}")
    else:
        print("✗ 스토어 정보 조회 실패")
        return False

    # 4. Dashboard API로 어제 데이터 수집
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    print(f"\n[어제 데이터: {yesterday}] — Dashboard API")
    data = fetch_daily_data(yesterday)
    if data and data.get('order_count', 0) > 0:
        print(f"\n  ── 매출 요약 ──")
        print(f"  결제합계:    {data['paid_amount']:,}원")
        print(f"  환불합계:    {data['refund_amount']:,}원")
        print(f"  순매출:      {data['net_sales']:,}원  (= 결제합계 - 환불합계)")
        print(f"  주문건수:    {data['order_count']}건")
        print(f"  구매자수:    {data['unique_customers']}명")
        print(f"  객단가:      {data['avg_order_value']:,}원")
        print(f"  상품구매금액: {data['product_amount']:,}원")
    else:
        print("  데이터 없음 (주문 0건)")

    # 5. Dashboard 날짜 범위 지원 여부 확인
    print(f"\n[날짜 범위 테스트] 7일 전 데이터 조회...")
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    stats = fetch_dashboard(week_ago, week_ago)
    range_ok = False
    for s in stats:
        if s.get('date') == week_ago:
            paid = int(_parse_money(s.get('paid_price', 0)))
            print(f"  ✓ {week_ago} 조회 성공: 결제합계 {paid:,}원")
            range_ok = True
            break
    if not range_ok:
        print(f"  ⚠ {week_ago} 데이터 없음 — Dashboard가 최근 2일만 반환할 수 있음")
        print(f"    → 백필 시 일별 개별 호출 필요")

    print("\n" + "=" * 50)
    print("테스트 완료")
    return True


# ============================================================
# 진입점
# ============================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Re:NK 카페24 API 데이터 수집기')
    parser.add_argument('--date', help='수집 날짜 (YYYY-MM-DD)')
    parser.add_argument('--since', help='시작일')
    parser.add_argument('--until', help='종료일')
    parser.add_argument('--test', action='store_true', help='API 연결 테스트')
    args = parser.parse_args()

    if args.test:
        test_connection()
    elif args.date:
        data = fetch_daily_data(args.date)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif args.since and args.until:
        data = fetch_range(args.since, args.until)
        print(f"\n총 {len(data)}일 수집 완료")
    else:
        # 기본: 어제 데이터
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        data = fetch_daily_data(yesterday)
        print(json.dumps(data, indent=2, ensure_ascii=False))
