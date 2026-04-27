#!/usr/bin/env python3
"""
Re:NK Google Sheets 백필 스크립트
==================================
Meta API → Google Sheets 일괄 기입 (배치 방식)

사용법:
  python backfill_sheets.py --since 2026-02-19 --until 2026-04-20 --own       # 자사몰만
  python backfill_sheets.py --since 2026-02-19 --until 2026-04-20 --ss        # 스마트스토어만
  python backfill_sheets.py --since 2026-02-19 --until 2026-04-20 --all       # 전체
  python backfill_sheets.py --since 2026-02-19 --until 2026-04-20 --all --dry-run
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta

# 상위 폴더 모듈 import용
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta_api_fetcher import fetch_account_insights, CONFIG
from google_sheets_writer import (
    load_config, get_access_token,
    check_date_and_next_row, make_meta_own_row, make_meta_ss_row,
    sheets_append,
)


def date_range(since: str, until: str) -> list:
    """시작일~종료일 사이 모든 날짜 리스트 생성"""
    start = datetime.strptime(since, '%Y-%m-%d')
    end = datetime.strptime(until, '%Y-%m-%d')
    dates = []
    d = start
    while d <= end:
        dates.append(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)
    return dates


ZERO_DATA = {
    'cost': 0, 'impressions': 0, 'clicks': 0,
    'purchases': 0, 'revenue': 0,
    'cpas_purchases': 0, 'cpas_revenue': 0,
    'views': 0, 'landing_page_views': 0, 'content_views': 0,
}


def backfill_meta_own(sid: str, token: str, since: str, until: str, dry_run: bool = False):
    """Meta 자사몰 백필"""
    print("\n" + "=" * 50)
    print(f"META 자사몰 백필: {since} ~ {until}")
    print("=" * 50)

    own_data = fetch_account_insights(
        CONFIG['ACCOUNT_OWN'], since, until, '자사몰'
    )
    if not own_data:
        own_data = {}

    exists, start_row = check_date_and_next_row(sid, 'META 자사몰', '__dummy__', token)
    print(f"시작 행: {start_row}")

    all_rows = []
    current_row = start_row
    filled = 0

    for date_str in date_range(since, until):
        d = own_data.get(date_str, ZERO_DATA)
        row = make_meta_own_row(date_str, d, current_row)
        all_rows.append(row)
        if d is not ZERO_DATA:
            filled += 1
        if dry_run:
            tag = "DATA" if d is not ZERO_DATA else "ZERO"
            print(f"  [{tag}] {date_str} → row {current_row}: 광고비 {int(d['cost']):,}원 | 매출 {int(d.get('revenue',0)):,}원")
        current_row += 1

    if dry_run:
        print(f"\n미리보기: {len(all_rows)}일 (데이터 {filled}일 / 빈날 {len(all_rows)-filled}일)")
        return

    print(f"{len(all_rows)}일 일괄 기입 중 (데이터 {filled}일 / 빈날 {len(all_rows)-filled}일)...")
    result = sheets_append(sid, "'META 자사몰'!A:M", all_rows, token)
    if result:
        print(f"완료: {len(all_rows)}일 (row {start_row}~{current_row - 1})")
    else:
        print("[FAIL] 기입 실패")


def backfill_meta_ss(sid: str, token: str, since: str, until: str, dry_run: bool = False):
    """Meta 스마트스토어 백필"""
    print("\n" + "=" * 50)
    print(f"META 스마트스토어 백필: {since} ~ {until}")
    print("=" * 50)

    ss_data = fetch_account_insights(
        CONFIG['ACCOUNT_SS'], since, until, '스마트스토어'
    )
    if not ss_data:
        ss_data = {}

    exists, start_row = check_date_and_next_row(sid, 'META 스마트스토어', '__dummy__', token)
    print(f"시작 행: {start_row}")

    all_rows = []
    current_row = start_row
    filled = 0

    for date_str in date_range(since, until):
        d = ss_data.get(date_str, ZERO_DATA)
        row = make_meta_ss_row(date_str, d, current_row)
        all_rows.append(row)
        if d is not ZERO_DATA:
            filled += 1
        if dry_run:
            tag = "DATA" if d is not ZERO_DATA else "ZERO"
            cpas_rev = int(d.get('cpas_revenue', 0))
            print(f"  [{tag}] {date_str} → row {current_row}: 광고비 {int(d['cost']):,}원 | CPAS전환값 {cpas_rev:,}원")
        current_row += 1

    if dry_run:
        print(f"\n미리보기: {len(all_rows)}일 (데이터 {filled}일 / 빈날 {len(all_rows)-filled}일)")
        return

    print(f"{len(all_rows)}일 일괄 기입 중 (데이터 {filled}일 / 빈날 {len(all_rows)-filled}일)...")
    result = sheets_append(sid, "'META 스마트스토어'!A:L", all_rows, token)
    if result:
        print(f"완료: {len(all_rows)}일 (row {start_row}~{current_row - 1})")
    else:
        print("[FAIL] 기입 실패")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Re:NK Sheets 백필')
    parser.add_argument('--since', required=True, help='시작일 (YYYY-MM-DD)')
    parser.add_argument('--until', required=True, help='종료일 (YYYY-MM-DD)')
    parser.add_argument('--own', action='store_true', help='META 자사몰만')
    parser.add_argument('--ss', action='store_true', help='META 스마트스토어만')
    parser.add_argument('--all', action='store_true', help='전체')
    parser.add_argument('--dry-run', action='store_true', help='실제 기입 없이 미리보기')
    args = parser.parse_args()

    # 인증
    config = load_config()
    if not config:
        sys.exit(1)
    sid = config['spreadsheet_id']
    token = get_access_token()
    if not token:
        print("[ERROR] Google Sheets 인증 실패")
        sys.exit(1)

    if args.own or args.all:
        backfill_meta_own(sid, token, args.since, args.until, args.dry_run)

    if args.ss or args.all:
        backfill_meta_ss(sid, token, args.since, args.until, args.dry_run)

    if not (args.own or args.ss or args.all):
        print("옵션을 지정하세요: --own / --ss / --all")
