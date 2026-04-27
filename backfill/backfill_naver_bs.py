#!/usr/bin/env python3
"""
네이버 브랜드검색(BS) 일할계산 광고비 백필
==========================================
기존 네이버 SA 시트에서 브검_광고비(F열)가 0인 행에
월 정액(253만원) / 해당월 일수 = 일할 광고비를 소급 적용.
총광고비(B열)에도 일할분 합산.

사용법:
  py backfill/backfill_naver_bs.py --since 2026-04-01 --until 2026-04-26
  py backfill/backfill_naver_bs.py --since 2026-04-01 --until 2026-04-26 --apply
  py backfill/backfill_naver_bs.py --revert --since 2026-01-23 --until 2026-03-31 --apply
"""
import sys, os, argparse, calendar, time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from google_sheets_writer import load_config, get_access_token, sheets_get, sheets_update

SHEET = '네이버 SA'
BS_MONTHLY_COST = 2_530_000  # 월 253만원
BATCH_SIZE = 25  # 배치당 행 수 (rate limit: 60 writes/min → 25행×2셀 = 50 writes)


def parse_int(val):
    if not val:
        return 0
    return int(str(val).replace(',', '').strip())


def calc_daily_cost(date_str: str) -> int:
    """날짜 → 해당 월 일할 광고비"""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    days_in_month = calendar.monthrange(dt.year, dt.month)[1]
    return round(BS_MONTHLY_COST / days_in_month)


def main():
    parser = argparse.ArgumentParser(description='네이버 BS 일할계산 백필')
    parser.add_argument('--since', required=True, help='시작일 (YYYY-MM-DD)')
    parser.add_argument('--until', required=True, help='종료일 (YYYY-MM-DD)')
    parser.add_argument('--apply', action='store_true', help='실제 시트 업데이트 (없으면 dry-run)')
    parser.add_argument('--revert', action='store_true', help='BS 광고비 되돌리기 (F→0, B에서 차감)')
    args = parser.parse_args()

    config = load_config()
    sid = config.get('spreadsheet_id', '')
    token = get_access_token()
    if not sid or not token:
        print("[ERROR] 인증 실패")
        return

    since_dt = datetime.strptime(args.since, '%Y-%m-%d')
    until_dt = datetime.strptime(args.until, '%Y-%m-%d')

    # 시트 데이터 읽기: A(날짜), B(총광고비), F(브검_광고비)
    result = sheets_get(sid, f"'{SHEET}'!A:F", token)
    rows = result.get('values', [])
    if not rows:
        print("[ERROR] 시트 데이터 없음")
        return

    mode = "REVERT" if args.revert else "BACKFILL"
    print(f"[{mode}] {args.since} ~ {args.until}")
    print(f"{'날짜':12s} {'현재총광고비':>12s} {'현재브검':>10s} → {'변경브검':>10s} {'새총광고비':>12s}")
    print("-" * 65)

    updates = []

    for i, row in enumerate(rows):
        if i == 0:
            continue
        if not row or len(row) < 1:
            continue

        date_str = row[0]
        try:
            row_dt = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            continue

        # 날짜 범위 필터
        if row_dt < since_dt or row_dt > until_dt:
            continue

        total_cost = parse_int(row[1]) if len(row) > 1 else 0
        bs_cost = parse_int(row[5]) if len(row) > 5 else 0
        row_num = i + 1

        if args.revert:
            # 되돌리기: F > 0인 행만 대상
            if bs_cost == 0:
                continue
            new_total = total_cost - bs_cost
            new_bs = 0
        else:
            # 백필: F == 0인 행만 대상
            if bs_cost > 0:
                continue
            daily_cost = calc_daily_cost(date_str)
            new_total = total_cost + daily_cost
            new_bs = daily_cost

        print(f"{date_str:12s} {total_cost:>12,} {bs_cost:>10,} → {new_bs:>10,} {new_total:>12,}")
        updates.append((row_num, date_str, new_total, new_bs))

    print("-" * 65)
    print(f"총 {len(updates)}건 {mode} 대상")

    if not args.apply:
        print(f"\n[DRY-RUN] --apply 옵션으로 실제 적용")
        return

    if not updates:
        print("업데이트 대상 없음")
        return

    # 배치 업데이트 (rate limit 방지: BATCH_SIZE행씩 → 1분 대기)
    total_batches = (len(updates) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(updates))
        batch = updates[start:end]

        if batch_idx > 0:
            wait = 65
            print(f"\n  ⏳ Rate limit 대기 ({wait}초)...", end='', flush=True)
            time.sleep(wait)
            print(" OK")

        print(f"\n  [배치 {batch_idx+1}/{total_batches}] {len(batch)}건")

        for row_num, date_str, new_total, new_bs in batch:
            # B열(총광고비) + F열(브검_광고비) 한번에 업데이트
            sheets_update(sid, f"'{SHEET}'!B{row_num}", [[new_total]], token)
            sheets_update(sid, f"'{SHEET}'!F{row_num}", [[new_bs]], token)
            print(f"  ✓ {date_str} (행 {row_num}): 총광고비={new_total:,} | 브검={new_bs:,}")

    print(f"\n{mode} 완료: {len(updates)}건 업데이트")


if __name__ == '__main__':
    main()
