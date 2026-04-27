#!/usr/bin/env python3
"""
네이버 SA 백필 → Google Sheets (캠페인 타입별 합산)
=====================================================
일별 1행: 총광고비, 총클릭, 구매완료전환수, 구매완료전환매출,
          브검/파워링크/쇼검 타입별 광고비·클릭·전환

사용법:
  python backfill_naver_sa.py --since 2026-01-23 --until 2026-04-21 --dry-run
  python backfill_naver_sa.py --since 2026-01-23 --until 2026-04-21
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

# 상위 폴더 모듈 import용
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from naver_api_fetcher import fetch_naver_data
from google_sheets_writer import (
    load_config, get_access_token,
    check_date_and_next_row, make_naver_row,
    sheets_append,
)


def date_range(since: str, until: str) -> list:
    start = datetime.strptime(since, '%Y-%m-%d')
    end = datetime.strptime(until, '%Y-%m-%d')
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    return dates


def backfill(since: str, until: str, dry_run: bool = False):
    print("=" * 60)
    print("네이버 SA → Google Sheets 백필 (캠페인 타입별)")
    print(f"기간: {since} ~ {until}")
    print("=" * 60)

    # 1. 네이버 API로 전체 기간 수집 (1일씩)
    dates = date_range(since, until)
    print(f"\n{len(dates)}일 수집 시작...\n")

    all_data = {}
    for di, date_str in enumerate(dates):
        result = fetch_naver_data(date_str, date_str)
        if result and date_str in result:
            all_data[date_str] = result[date_str]
            d = result[date_str]
            sa = d['sa']
            print(f"  [{di+1:>3}/{len(dates)}] {date_str} → "
                  f"광고비 {sa['cost']:>10,}원 | 클릭 {sa['clicks']:>4} | "
                  f"구매전환 {sa['purchase_count']:>3}건 | 구매매출 {sa['purchase_revenue']:>12,}원")
        else:
            print(f"  [{di+1:>3}/{len(dates)}] {date_str} → 데이터 없음")

    if not all_data:
        print("[ERROR] 수집 데이터 없음")
        return

    print(f"\n수집 완료: {len(all_data)}일")

    if dry_run:
        # 합산 요약
        total_cost = sum(d['sa']['cost'] for d in all_data.values())
        total_pcnt = sum(d['sa']['purchase_count'] for d in all_data.values())
        total_prev = sum(d['sa']['purchase_revenue'] for d in all_data.values())
        print(f"\n미리보기 합산:")
        print(f"  총광고비: {total_cost:,}원")
        print(f"  구매완료 전환수: {total_pcnt:,}건")
        print(f"  구매완료 전환매출: {total_prev:,}원")
        return

    # 2. Google Sheets 기입
    config = load_config()
    if not config:
        return
    sid = config['spreadsheet_id']
    token = get_access_token()
    if not token:
        print("[ERROR] Google Sheets 인증 실패")
        return

    _, start_row = check_date_and_next_row(sid, '네이버 SA', '__dummy__', token)
    print(f"\n시작 행: {start_row}")

    all_rows = []
    current_row = start_row
    for date_str in sorted(all_data.keys()):
        row = make_naver_row(date_str, all_data[date_str], current_row)
        all_rows.append(row)
        current_row += 1

    print(f"{len(all_rows)}일 일괄 기입 중...")
    result = sheets_append(sid, "'네이버 SA'!A:P", all_rows, token)
    if result:
        print(f"완료: {len(all_rows)}일 (row {start_row}~{current_row - 1})")
    else:
        print("[FAIL] 기입 실패")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='네이버 SA 백필')
    parser.add_argument('--since', required=True, help='시작일 (YYYY-MM-DD)')
    parser.add_argument('--until', required=True, help='종료일 (YYYY-MM-DD)')
    parser.add_argument('--dry-run', action='store_true', help='미리보기')
    args = parser.parse_args()

    backfill(args.since, args.until, args.dry_run)
