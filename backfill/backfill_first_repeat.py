#!/usr/bin/env python3
"""
카페24 첫구매/재구매 소급 백필
================================
2026-02-19 ~ 어제까지 날짜별로 첫구매/재구매 수를 조회하여
Google Sheets '카페24 커머스' 시트 G(첫구매), H(재구매) 열에 기입

사용법:
  py backfill_first_repeat.py                              # 2/19~어제 전체
  py backfill_first_repeat.py --since 2026-03-01           # 3/1~어제
  py backfill_first_repeat.py --since 2026-04-01 --until 2026-04-10  # 범위 지정
  py backfill_first_repeat.py --dry-run                    # 실제 기입 없이 확인만
"""

import sys
import os
import time
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cafe24_api_fetcher import _count_first_repeat
from google_sheets_writer import (
    load_config, get_access_token, sheets_get, sheets_update
)

SHEET_NAME = '카페24 커머스'


def find_date_row_map(sid, token):
    """시트에서 날짜 → 행번호 매핑 생성"""
    result = sheets_get(sid, f"'{SHEET_NAME}'!A:A", token)
    rows = result.get('values', [])
    date_map = {}
    for i, row in enumerate(rows):
        if row and i >= 1:  # 헤더 제외
            date_map[row[0]] = i + 1  # 1-based row number
    return date_map


def backfill(since, until, dry_run=False):
    # Google Sheets 인증
    config = load_config()
    if not config:
        print("[ERROR] Google Sheets 설정 없음")
        return False

    sid = config.get('spreadsheet_id', '')
    token = get_access_token()
    if not sid or not token:
        print("[ERROR] 인증 실패")
        return False

    # 시트에서 날짜-행 매핑
    date_map = find_date_row_map(sid, token)
    print(f"시트 데이터 행: {len(date_map)}건")

    # 날짜 범위 생성
    current = datetime.strptime(since, '%Y-%m-%d')
    end = datetime.strptime(until, '%Y-%m-%d')
    dates = []
    while current <= end:
        dates.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)

    print(f"백필 대상: {since} ~ {until} ({len(dates)}일)")
    print(f"{'DRY RUN - 실제 기입 없음' if dry_run else '실제 기입 모드'}")
    print("=" * 60)

    success_count = 0
    skip_count = 0
    error_count = 0

    for i, date_str in enumerate(dates):
        row_num = date_map.get(date_str)
        if not row_num:
            print(f"  [{i+1}/{len(dates)}] {date_str}: 시트에 해당 날짜 행 없음 → SKIP")
            skip_count += 1
            continue

        print(f"  [{i+1}/{len(dates)}] {date_str} (행 {row_num}): API 조회 중...", end='', flush=True)

        try:
            fr = _count_first_repeat(date_str)
            first = fr.get('first_buyers', 0)
            repeat = fr.get('repeat_buyers', 0)
            total = first + repeat

            print(f" 첫구매={first}, 재구매={repeat}, 총={total}")

            if not dry_run:
                # G열(첫구매), H열(재구매)만 업데이트
                result = sheets_update(
                    sid,
                    f"'{SHEET_NAME}'!G{row_num}:H{row_num}",
                    [[first, repeat]],
                    token
                )
                if result:
                    print(f"    → 시트 기입 완료")
                    success_count += 1
                else:
                    print(f"    → 시트 기입 실패")
                    error_count += 1
            else:
                success_count += 1

            # API 부하 방지
            time.sleep(1)

        except Exception as e:
            print(f" ERROR: {e}")
            error_count += 1
            time.sleep(2)

    print("=" * 60)
    print(f"완료: 성공 {success_count} / 스킵 {skip_count} / 에러 {error_count}")
    return error_count == 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='카페24 첫구매/재구매 소급 백필')
    parser.add_argument('--since', default='2026-02-19', help='시작일 (기본: 2026-02-19)')
    parser.add_argument('--until', default=None, help='종료일 (기본: 어제)')
    parser.add_argument('--dry-run', action='store_true', help='실제 기입 없이 확인만')
    args = parser.parse_args()

    if not args.until:
        args.until = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    backfill(args.since, args.until, args.dry_run)
