#!/usr/bin/env python3
"""
카페24 커머스 시트 4/21~4/26 누락 데이터 일괄 수정
===================================================
- 방문자수: 카페24 애널리틱스 순방문(명) 기준
- 결제합계/환불합계: 카페24 대시보드 기준
- 상품구매금액: 카페24 대시보드 기준

사용법:
  py fix_cafe24_0421_0426.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from google_sheets_writer import (
    load_config, get_access_token, sheets_get, sheets_update
)

SHEET = '카페24 커머스'

# 대시보드 + 애널리틱스 기준 정확한 값
# 열 매핑: B=결제합계, C=환불합계, K=방문자수, M=상품구매금액
FIXES = {
    '2026-04-21': {
        'paid_amount': 5040000,       # B: 대시보드 결제합계
        'refund_amount': 467000,      # C: 대시보드 환불합계 (기존 0)
        'visitor_count': 1114,        # K: 애널리틱스 순방문
        'product_amount': 24011800,   # M: 대시보드 상품구매금액
    },
    '2026-04-22': {
        'paid_amount': 7113400,       # B: 이미 OK
        'refund_amount': 481000,      # C: 이미 OK
        'visitor_count': 1056,        # K: 애널리틱스 순방문
        'product_amount': 33923500,   # M: 이미 OK (기존 시트에 있음)
    },
    '2026-04-23': {
        'visitor_count': 1906,        # K: 애널리틱스 순방문
        # 결제/환불/상품금액은 이미 정확
    },
    '2026-04-24': {
        'paid_amount': 6934400,       # B: 대시보드 기준 수정
        'refund_amount': 294000,      # C: 대시보드 기준 수정
        'visitor_count': 1001,        # K: 애널리틱스 순방문
        'product_amount': 31002600,   # M: 대시보드 상품구매금액
    },
    '2026-04-25': {
        'paid_amount': 271500,        # B: 대시보드 기준 수정
        'refund_amount': 0,           # C
        'visitor_count': 458,         # K: 애널리틱스 순방문
        'product_amount': 491600,     # M: 대시보드 상품구매금액
    },
    '2026-04-26': {
        'paid_amount': 656000,        # B: 이미 OK
        'refund_amount': 0,           # C: 이미 OK
        'visitor_count': 568,         # K: GA4 users 대체 (카페24 애널리틱스 미갱신)
        'product_amount': 1251000,    # M: 대시보드 상품구매금액
    },
}


def main():
    config = load_config()
    sid = config.get('spreadsheet_id', '')
    token = get_access_token()
    if not sid or not token:
        print("[ERROR] 인증 실패")
        return

    # 날짜 → 행번호 매핑
    result = sheets_get(sid, f"'{SHEET}'!A:A", token)
    rows = result.get('values', [])
    date_map = {}
    for i, row in enumerate(rows):
        if row and i >= 1:
            date_map[row[0]] = i + 1

    for date_str in sorted(FIXES.keys()):
        fix = FIXES[date_str]
        row_num = date_map.get(date_str)
        if not row_num:
            print(f"  {date_str}: 시트에 행 없음 → SKIP")
            continue

        updates = []

        # B(결제합계), C(환불합계) → D(순매출)은 =B-C 수식 자동 계산
        if 'paid_amount' in fix:
            paid = fix['paid_amount']
            refund = fix.get('refund_amount', 0)
            sheets_update(sid, f"'{SHEET}'!B{row_num}:C{row_num}",
                          [[paid, refund]], token)
            updates.append(f"결제 {paid:,} | 환불 {refund:,}")

        # K(방문자수)
        if 'visitor_count' in fix and fix['visitor_count'] > 0:
            sheets_update(sid, f"'{SHEET}'!K{row_num}",
                          [[fix['visitor_count']]], token)
            updates.append(f"방문자 {fix['visitor_count']:,}")

        # M(상품구매금액)
        if 'product_amount' in fix and fix['product_amount'] > 0:
            sheets_update(sid, f"'{SHEET}'!M{row_num}",
                          [[fix['product_amount']]], token)
            updates.append(f"상품금액 {fix['product_amount']:,}")

        print(f"  {date_str} (행 {row_num}): {' | '.join(updates)}")

    print("\n수정 완료!")


if __name__ == '__main__':
    main()
