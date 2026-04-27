#!/usr/bin/env python3
"""
Slack 보고서 일괄 발행 (하나의 메시지에 여러 파일 묶어서 전송)
=============================================================

사용법:
  py slack_batch.py 2026-04-24 2026-04-25 2026-04-26
  py slack_batch.py --since 2026-04-24 --until 2026-04-26
"""
import sys, os, argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slack_uploader import load_config, find_report, upload_multiple_files


def main():
    parser = argparse.ArgumentParser(description='Slack 보고서 일괄 발행')
    parser.add_argument('dates', nargs='*', help='날짜 목록 (YYYY-MM-DD)')
    parser.add_argument('--since', help='시작일')
    parser.add_argument('--until', help='종료일')
    args = parser.parse_args()

    # 날짜 목록 생성
    dates = []
    if args.since and args.until:
        current = datetime.strptime(args.since, '%Y-%m-%d')
        end = datetime.strptime(args.until, '%Y-%m-%d')
        while current <= end:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
    elif args.dates:
        dates = args.dates
    else:
        print("사용법: py slack_batch.py 2026-04-24 2026-04-25 2026-04-26")
        print("    또는: py slack_batch.py --since 2026-04-24 --until 2026-04-26")
        sys.exit(1)

    # Slack 설정 로드
    config = load_config()
    if not config:
        sys.exit(1)

    token = config.get('user_token') or config.get('bot_token')
    channel = config.get('channel_id', '')
    if not token or not channel:
        print("[ERROR] Slack 토큰 또는 채널 미설정")
        sys.exit(1)

    # 보고서 파일 수집
    file_paths = []
    for date_str in dates:
        report = find_report(date_str)
        if report:
            file_paths.append(report)
            print(f"  {date_str}: {os.path.basename(report)}")
        else:
            print(f"  {date_str}: 보고서 파일 없음 → SKIP")

    if not file_paths:
        print("[ERROR] 업로드할 보고서 없음")
        sys.exit(1)

    # 메시지
    date_range = f"{dates[0]} ~ {dates[-1]}"
    comment = f"📊 Re:NK Daily Report ({date_range})"

    # 하나의 메시지로 묶어서 업로드
    print(f"\nSlack 일괄 발행: {len(file_paths)}건 → 1개 메시지")
    print("=" * 50)
    success = upload_multiple_files(file_paths, channel, token, message=comment)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
