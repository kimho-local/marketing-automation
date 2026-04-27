#!/usr/bin/env python3
"""
카페24 CSV 백필 → Google Sheets
==================================
카페24 대시보드 매출 CSV + 방문자/구매자 CSV 병합 → Google Sheets 기입

사용법:
  python backfill_cafe24_csv.py --sales DailyList.csv --visitors 방문자.csv --dry-run
  python backfill_cafe24_csv.py --sales DailyList.csv --visitors 방문자.csv
"""

import os
import sys
import csv
import argparse
from datetime import datetime

# 상위 폴더 모듈 import용
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_sheets_writer import (
    load_config, get_access_token,
    check_date_and_next_row, make_cafe24_row,
    sheets_append,
)


# ============================================================
# 파싱 유틸
# ============================================================

def parse_money(val: str) -> int:
    """금액 문자열 → 정수"""
    if not val:
        return 0
    cleaned = str(val).replace(',', '').replace('"', '').replace('원', '').strip()
    try:
        return int(float(cleaned))
    except ValueError:
        return 0


def parse_date(val: str) -> str:
    """날짜 파싱: '2026-04-21(화)' → '2026-04-21'"""
    val = val.strip().replace('"', '')
    if '(' in val:
        val = val[:val.index('(')].strip()
    for fmt in ['%Y-%m-%d', '%Y/%m/%d']:
        try:
            return datetime.strptime(val, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return ''


def detect_encoding(file_path: str) -> str:
    """파일 인코딩 자동 감지"""
    for enc in ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                f.read(500)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return 'utf-8'


# ============================================================
# 매출 CSV 파싱 (DailyList.csv)
# ============================================================

def read_sales_csv(file_path: str) -> dict:
    """
    카페24 매출 CSV 파싱
    헤더: 일자, 주문수, 품목수, 상품구매금액, 배송비, 할인, 쿠폰,
          실결제금액, ..., 결제합계, 환불합계, 순매출

    반환: { '2026-04-21': { paid_amount, refund_amount, ... }, ... }
    """
    enc = detect_encoding(file_path)
    with open(file_path, 'r', encoding=enc) as f:
        lines = f.readlines()

    # 헤더 행 찾기 (일자 + 결제합계 포함된 행)
    header_idx = None
    for i, line in enumerate(lines):
        if '일자' in line and '결제합계' in line:
            header_idx = i
            break

    if header_idx is None:
        print(f"[ERROR] 매출 CSV 헤더를 찾을 수 없음: {file_path}")
        return {}

    reader = csv.reader(lines[header_idx:])
    rows = list(reader)
    header = [h.strip().replace('"', '') for h in rows[0]]

    # 컬럼 인덱스
    col = {}
    for i, h in enumerate(header):
        if h == '일자':
            col['date'] = i
        elif h == '결제합계':
            col['paid'] = i
        elif h == '환불합계':
            col['refund'] = i
        elif h == '순매출':
            col['net'] = i
        elif h == '주문수':
            col['orders'] = i
        elif h == '상품구매금액':
            col['product'] = i

    print(f"매출 CSV: {file_path} (인코딩: {enc})")
    print(f"  헤더: {header}")
    print(f"  컬럼 매핑: {col}")

    data = {}
    for row in rows[1:]:
        if not row or len(row) < max(col.values()) + 1:
            continue

        date_str = parse_date(row[col['date']])
        if not date_str:
            continue

        data[date_str] = {
            'paid_amount': parse_money(row[col['paid']]),
            'refund_amount': parse_money(row[col['refund']]),
            'net_sales': parse_money(row[col['net']]),
            'order_count': parse_money(row[col['orders']]),
            'product_amount': parse_money(row[col['product']]),
        }

    print(f"  파싱 완료: {len(data)}일")
    return data


# ============================================================
# 방문자/구매자 CSV 파싱
# ============================================================

def read_visitors_csv(file_path: str) -> dict:
    """
    방문자/구매자 CSV 파싱
    헤더: date, visitor_count, buyer_count, order_count, purchase_rate

    반환: { '2026-04-21': { visitor_count, buyer_count }, ... }
    """
    enc = detect_encoding(file_path)
    with open(file_path, 'r', encoding=enc) as f:
        reader = csv.DictReader(f)
        data = {}
        for row in reader:
            date_str = row.get('date', '').strip()
            if not date_str:
                continue
            data[date_str] = {
                'visitor_count': int(row.get('visitor_count', 0)),
                'buyer_count': int(row.get('buyer_count', 0)),
            }

    print(f"방문자 CSV: {file_path} (인코딩: {enc})")
    print(f"  파싱 완료: {len(data)}일")
    return data


# ============================================================
# 병합 & 백필
# ============================================================

def merge_data(sales: dict, visitors: dict) -> list:
    """매출 + 방문자/구매자 데이터 병합 → 날짜순 리스트"""
    all_dates = sorted(set(list(sales.keys()) + list(visitors.keys())))

    merged = []
    for date_str in all_dates:
        s = sales.get(date_str, {})
        v = visitors.get(date_str, {})

        paid = s.get('paid_amount', 0)
        refund = s.get('refund_amount', 0)
        orders = s.get('order_count', 0)
        net = s.get('net_sales', paid - refund)

        merged.append({
            'date': date_str,
            'paid_amount': paid,
            'refund_amount': refund,
            'net_sales': net,
            'order_count': orders,
            'unique_customers': v.get('buyer_count', 0),
            'visitor_count': v.get('visitor_count', 0),
            'avg_order_value': int(net / orders) if orders > 0 else 0,
            'product_amount': s.get('product_amount', 0),
        })

    return merged


def backfill(sales_file: str, visitors_file: str, dry_run: bool = False):
    """CSV 파싱 → 병합 → Google Sheets 일괄 기입"""
    print("=" * 50)
    print("카페24 CSV → Google Sheets 백필")
    print("=" * 50)

    # 1. CSV 파싱
    sales = read_sales_csv(sales_file)
    visitors = read_visitors_csv(visitors_file)

    if not sales:
        print("[ERROR] 매출 데이터 없음")
        return

    # 2. 병합
    merged = merge_data(sales, visitors)
    print(f"\n병합 완료: {len(merged)}일")
    print(f"  기간: {merged[0]['date']} ~ {merged[-1]['date']}")

    # 3. Google Sheets 인증
    config = load_config()
    if not config:
        return
    sid = config['spreadsheet_id']
    token = get_access_token()
    if not token:
        print("[ERROR] Google Sheets 인증 실패")
        return

    # 4. 시작 행 확인
    exists, start_row = check_date_and_next_row(sid, '카페24 커머스', '__dummy__', token)
    print(f"시작 행: {start_row}")

    # 5. 행 생성
    all_rows = []
    current_row = start_row
    filled = 0

    for d in merged:
        row = make_cafe24_row(d['date'], d, current_row)
        all_rows.append(row)
        if d['paid_amount'] > 0 or d['order_count'] > 0:
            filled += 1

        if dry_run:
            tag = "DATA" if d['paid_amount'] > 0 else "ZERO"
            print(f"  [{tag}] {d['date']} → row {current_row}: "
                  f"결제 {d['paid_amount']:,} | 환불 {d['refund_amount']:,} | "
                  f"순매출 {d['net_sales']:,} | 주문 {d['order_count']}건 | "
                  f"구매자 {d['unique_customers']}명 | 방문자 {d['visitor_count']}명")
        current_row += 1

    if dry_run:
        print(f"\n미리보기: {len(all_rows)}일 (데이터 {filled}일 / 빈날 {len(all_rows)-filled}일)")
        return

    # 6. 일괄 기입
    print(f"\n{len(all_rows)}일 일괄 기입 중...")
    result = sheets_append(sid, "'카페24 커머스'!A:K", all_rows, token)
    if result:
        print(f"완료: {len(all_rows)}일 (row {start_row}~{current_row - 1})")
    else:
        print("[FAIL] 기입 실패")


# ============================================================
# CLI
# ============================================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='카페24 CSV → Google Sheets 백필')
    parser.add_argument('--sales', required=True, help='매출 CSV (DailyList.csv)')
    parser.add_argument('--visitors', required=True, help='방문자/구매자 CSV')
    parser.add_argument('--dry-run', action='store_true', help='미리보기')
    args = parser.parse_args()

    for f in [args.sales, args.visitors]:
        if not os.path.exists(f):
            print(f"[ERROR] 파일 없음: {f}")
            sys.exit(1)

    backfill(args.sales, args.visitors, args.dry_run)
