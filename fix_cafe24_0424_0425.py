#!/usr/bin/env python3
"""
4/24, 4/25 카페24 시트 데이터 수정
— Dashboard API 범위 밖이라 주문 API fallback으로 집계된 오차 보정
— 대시보드 실제값으로 덮어쓰기
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from google_sheets_writer import (
    load_config, get_access_token, sheets_get, sheets_update
)

SHEET = '카페24 커머스'

# 대시보드 기준 정확한 값 (결제합계, 환불합계, 상품구매금액)
FIXES = {
    '2026-04-24': {'paid_amount': 6934400, 'refund_amount': 294000, 'product_amount': 31002600},
    '2026-04-25': {'paid_amount': 271500,  'refund_amount': 0,      'product_amount': 491600},
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

    for date_str, fix in FIXES.items():
        row_num = date_map.get(date_str)
        if not row_num:
            print(f"  {date_str}: 행 없음 → SKIP")
            continue

        n = row_num
        # B: 결제합계, C: 환불합계, D: 순매출(수식), M: 상품구매금액
        paid = fix['paid_amount']
        refund = fix['refund_amount']
        product = fix['product_amount']

        # B, C 업데이트 (D는 =B-C 수식이므로 자동 계산)
        sheets_update(sid, f"'{SHEET}'!B{n}:C{n}", [[paid, refund]], token)

        # M(상품구매금액) 업데이트
        sheets_update(sid, f"'{SHEET}'!M{n}", [[product]], token)

        net = paid - refund
        print(f"  {date_str} (행 {n}): 결제 {paid:,} | 환불 {refund:,} | 순매출 {net:,} | 상품금액 {product:,}")

    print("\n수정 완료!")


if __name__ == '__main__':
    main()
