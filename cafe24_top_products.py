#!/usr/bin/env python3
"""
카페24 상품별 판매 TOP N 조회
==============================
주문 API (embed=items) → 상품별 실결제금액 집계

사용법:
  python cafe24_top_products.py --date 2026-04-23
  python cafe24_top_products.py --date 2026-04-23 --top 5
  python cafe24_top_products.py --since 2026-04-01 --until 2026-04-23 --top 10
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cafe24_api_fetcher import api_get


def _money(val) -> int:
    """금액 문자열/숫자 → int"""
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        try:
            return int(float(val.replace(',', '').strip()))
        except ValueError:
            return 0
    return 0


def aggregate_products(date_str: str) -> list:
    """
    주문 목록을 embed=items로 한 번에 가져와 상품별 집계
    — 개별 주문 상세 호출 없이 빠르게 처리
    """
    start = f"{date_str}T00:00:00+09:00"
    end = f"{date_str}T23:59:59+09:00"

    products = defaultdict(lambda: {
        'product_name': '',
        'product_no': 0,
        'quantity': 0,
        'amount': 0,          # 실결제금액 (할인 차감 후)
        'original_amount': 0,  # 원가 금액 (참고용)
        'order_count': 0,
    })

    offset = 0
    limit = 100
    total_orders = 0

    print(f"[1] {date_str} 주문+상품 조회 중 (embed=items)...")

    while True:
        result = api_get('/admin/orders', {
            'start_date': start,
            'end_date': end,
            'limit': limit,
            'offset': offset,
            'embed': 'items',
        })
        orders = result.get('orders', [])
        if not orders:
            break

        total_orders += len(orders)

        for o in orders:
            items = o.get('items', [])
            if not items:
                continue

            # 주문 단위 결제금액 (할인 후 실결제)
            order_paid = _money(o.get('payment_amount', 0))

            # 상품별 정가 합계 (안분 기준)
            item_totals = []
            for item in items:
                qty = int(item.get('quantity', 0) or 0)
                unit_price = _money(item.get('product_price', 0))
                item_totals.append(unit_price * qty)
            product_sum = sum(item_totals)

            for idx, item in enumerate(items):
                pno = item.get('product_no', 0)
                pname = item.get('product_name', '알수없음')
                qty = int(item.get('quantity', 0) or 0)
                original = item_totals[idx]

                # 실결제금액: 주문 결제금액을 정가 비중으로 안분
                if product_sum > 0 and order_paid > 0:
                    actual = int(order_paid * original / product_sum)
                else:
                    actual = 0

                key = pno or pname
                products[key]['product_name'] = pname
                products[key]['product_no'] = pno
                products[key]['quantity'] += qty
                products[key]['amount'] += actual
                products[key]['original_amount'] += original
                products[key]['order_count'] += 1

        if len(orders) < limit:
            break
        offset += limit
        time.sleep(0.5)  # Rate Limit 방지

    print(f"    주문 {total_orders}건 / 상품 {len(products)}종")

    ranked = sorted(products.values(), key=lambda x: x['amount'], reverse=True)
    return ranked


def fetch_top_products(date_str: str, top_n: int = 3) -> list:
    """
    외부 호출용: 해당 날짜 상품 TOP N 반환
    run_daily.py에서 호출

    반환: [
        {'product_name': '...', 'quantity': 5, 'amount': 150000, 'order_count': 3},
        ...
    ]
    """
    ranked = aggregate_products(date_str)
    return ranked[:top_n]


def print_top(ranked: list, top_n: int, date_str: str):
    """TOP N 출력"""
    print()
    print("=" * 65)
    print(f"  카페24 상품 판매 TOP {top_n} — {date_str}")
    print("=" * 65)

    if not ranked:
        print("  데이터 없음")
        return

    for i, p in enumerate(ranked[:top_n]):
        print(f"\n  #{i+1}  {p['product_name']}")
        print(f"       판매수량: {p['quantity']}개  |  실결제금액: {p['amount']:,}원  |  주문건수: {p['order_count']}건")
        if p.get('original_amount', 0) > 0 and p['original_amount'] != p['amount']:
            diff = p['original_amount'] - p['amount']
            print(f"       (정가합계: {p['original_amount']:,}원 → 할인: -{diff:,}원)")

    # 전체 요약
    total_qty = sum(p['quantity'] for p in ranked)
    total_amt = sum(p['amount'] for p in ranked)
    total_orig = sum(p.get('original_amount', 0) for p in ranked)
    print(f"\n{'─' * 65}")
    print(f"  전체 상품 종류: {len(ranked)}개")
    print(f"  총 판매수량: {total_qty}개  |  총 실결제금액: {total_amt:,}원")
    if total_orig > 0 and total_orig != total_amt:
        print(f"  (정가합계: {total_orig:,}원 → 총 할인: -{total_orig - total_amt:,}원)")
    print("=" * 65)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='카페24 상품별 판매 TOP N')
    parser.add_argument('--date', help='조회 날짜 (YYYY-MM-DD)')
    parser.add_argument('--since', help='시작일')
    parser.add_argument('--until', help='종료일')
    parser.add_argument('--top', type=int, default=3, help='TOP N (기본 3)')
    parser.add_argument('--json', action='store_true', help='JSON 출력')
    args = parser.parse_args()

    if args.date:
        dates = [args.date]
    elif args.since and args.until:
        dates = []
        cur = datetime.strptime(args.since, '%Y-%m-%d')
        end = datetime.strptime(args.until, '%Y-%m-%d')
        while cur <= end:
            dates.append(cur.strftime('%Y-%m-%d'))
            cur += timedelta(days=1)
    else:
        dates = [(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')]

    # 날짜 범위면 전체 합산
    all_products = defaultdict(lambda: {
        'product_name': '', 'product_no': 0,
        'quantity': 0, 'amount': 0, 'order_count': 0,
    })

    for d in dates:
        ranked = aggregate_products(d)
        for p in ranked:
            key = p['product_no'] or p['product_name']
            all_products[key]['product_name'] = p['product_name']
            all_products[key]['product_no'] = p['product_no']
            all_products[key]['quantity'] += p['quantity']
            all_products[key]['amount'] += p['amount']
            all_products[key]['order_count'] += p['order_count']

    final = sorted(all_products.values(), key=lambda x: x['amount'], reverse=True)

    period = dates[0] if len(dates) == 1 else f"{dates[0]} ~ {dates[-1]}"

    if args.json:
        print(json.dumps(final[:args.top], indent=2, ensure_ascii=False))
    else:
        print_top(final, args.top, period)
