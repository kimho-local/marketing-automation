#!/usr/bin/env python3
"""
Google Ads 시트 백필 스크립트
Google Ads 데이터만 수집 → Google Sheets 기입
"""
import os
import sys
import time
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google_ads_fetcher import fetch_google_data
from google_sheets_writer import (
    load_config, get_access_token, sheets_get, sheets_append,
    check_date_and_next_row, make_google_ads_row, initialize_sheets
)


def backfill(since: str, until: str, force: bool = False):
    print("=" * 60)
    print(f"Google Ads 백필: {since} ~ {until}")
    print("=" * 60)

    # 1. Google Ads 데이터 수집
    print("\n[1] Google Ads 데이터 수집...")
    data = fetch_google_data(since, until)
    if not data:
        print("  데이터 없음 — 종료")
        return

    dates = sorted(data.keys())
    print(f"  {len(dates)}일 데이터 수집 완료 ({dates[0]} ~ {dates[-1]})")

    # 2. Sheets 연결
    config = load_config()
    if not config:
        return
    sid = config.get('spreadsheet_id', '')
    token = get_access_token()
    if not sid or not token:
        return

    # 3. 시트 기입
    print(f"\n[2] Google Sheets 기입 중...")
    success = 0
    skip = 0
    fail = 0

    for d in dates:
        day_data = data[d]
        total = day_data.get('total', {})
        if total.get('cost', 0) <= 0:
            continue

        exists, next_row, _ = check_date_and_next_row(sid, 'Google Ads', d, token)

        if exists and not force:
            print(f"  [SKIP] {d} 이미 존재")
            skip += 1
            continue

        row = make_google_ads_row(d, day_data, next_row)
        result = sheets_append(sid, "'Google Ads'!A:M", [row], token)

        if result:
            print(f"  ✓ {d}: 광고비 {total['cost']:,}원 | 클릭 {total['clicks']} | 전환 {total.get('conversions',0):.0f}")
            success += 1
        else:
            print(f"  ✗ {d}: 기입 실패")
            fail += 1

        # Rate Limit 방지: 매 5행마다 2초 대기
        if (success + skip + fail) % 5 == 0:
            time.sleep(2)

    print(f"\n{'=' * 60}")
    print(f"백필 완료: 성공 {success} | 건너뜀 {skip} | 실패 {fail}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Google Ads 시트 백필')
    parser.add_argument('--since', required=True, help='시작일 (YYYY-MM-DD)')
    parser.add_argument('--until', required=True, help='종료일 (YYYY-MM-DD)')
    parser.add_argument('--force', action='store_true', help='기존 데이터 무시하고 추가')
    args = parser.parse_args()
    backfill(args.since, args.until, args.force)
