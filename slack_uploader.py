#!/usr/bin/env python3
"""
Re:NK Slack 보고서 파일 업로더
================================
docx 보고서를 #팀-브랜드-1파트 채널에 자동 업로드

사용법:
  python slack_uploader.py reports/ReNK_Daily_Report_2026-04-22(수).docx
  python slack_uploader.py --date 2026-04-22
  python slack_uploader.py --test
"""

import os
import sys
import json
import glob
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta


# ============================================================
# 설정
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'config', 'renk_slack_config.json')
REPORT_DIR = os.path.join(SCRIPT_DIR, 'reports')

SLACK_UPLOAD_URL = 'https://slack.com/api/files.getUploadURLExternal'
SLACK_COMPLETE_URL = 'https://slack.com/api/files.completeUploadExternal'
SLACK_POST_URL = 'https://slack.com/api/chat.postMessage'


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        print("[ERROR] config/renk_slack_config.json 파일 없음")
        return {}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================
# Slack API 호출
# ============================================================

def slack_api(url: str, token: str, data: dict = None, file_bytes: bytes = None, content_type: str = None) -> dict:
    """Slack API 호출 (JSON 또는 파일 업로드)"""
    headers = {'Authorization': f'Bearer {token}'}

    if file_bytes:
        # 파일 바이너리 업로드
        headers['Content-Type'] = content_type or 'application/octet-stream'
        req = urllib.request.Request(url, data=file_bytes, headers=headers, method='POST')
    elif data:
        body = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json; charset=utf-8'
        req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    else:
        req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f"[ERROR] Slack API (HTTP {e.code}): {body[:300]}")
        return {}
    except Exception as e:
        print(f"[ERROR] Slack API: {e}")
        return {}


def upload_file_to_channel(file_path: str, channel_id: str, token: str, message: str = None) -> bool:
    """
    Slack 파일 업로드 (v2 API: getUploadURLExternal → PUT → completeUploadExternal)
    """
    if not os.path.exists(file_path):
        print(f"[ERROR] 파일 없음: {file_path}")
        return False

    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    print(f"[INFO] Slack 파일 업로드: {filename} ({file_size:,} bytes)")

    # Step 1: 업로드 URL 발급
    params = urllib.parse.urlencode({
        'filename': filename,
        'length': file_size,
    })
    url = f"{SLACK_UPLOAD_URL}?{params}"
    result = slack_api(url, token)

    if not result.get('ok'):
        print(f"[ERROR] 업로드 URL 발급 실패: {result.get('error', '?')}")
        return False

    upload_url = result['upload_url']
    file_id = result['file_id']

    # Step 2: 파일 바이너리 업로드
    with open(file_path, 'rb') as f:
        file_bytes = f.read()

    req = urllib.request.Request(upload_url, data=file_bytes, method='POST')
    req.add_header('Content-Type', 'application/octet-stream')
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
    except Exception as e:
        print(f"[ERROR] 파일 업로드 실패: {e}")
        return False

    # Step 3: 업로드 완료 + 채널 공유
    complete_data = {
        'files': [{'id': file_id, 'title': filename}],
        'channel_id': channel_id,
    }
    if message:
        complete_data['initial_comment'] = message

    result = slack_api(SLACK_COMPLETE_URL, token, data=complete_data)

    if result.get('ok'):
        print(f"✓ Slack 업로드 완료: #{channel_id} → {filename}")
        return True
    else:
        print(f"[ERROR] 업로드 완료 실패: {result.get('error', '?')}")
        return False


# ============================================================
# 보고서 파일 찾기
# ============================================================

def upload_multiple_files(file_paths: list, channel_id: str, token: str, message: str = None) -> bool:
    """
    여러 파일을 하나의 Slack 메시지로 묶어서 업로드
    v2 API: 파일별 getUploadURLExternal → PUT → 전체 completeUploadExternal (files 배열)
    """
    if not file_paths:
        print("[ERROR] 업로드할 파일 없음")
        return False

    uploaded_files = []

    for file_path in file_paths:
        if not os.path.exists(file_path):
            print(f"[WARN] 파일 없음: {file_path} → SKIP")
            continue

        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        print(f"  [{len(uploaded_files)+1}/{len(file_paths)}] {filename} ({file_size:,} bytes) 업로드 중...", end='', flush=True)

        # Step 1: 업로드 URL 발급
        params = urllib.parse.urlencode({'filename': filename, 'length': file_size})
        result = slack_api(f"{SLACK_UPLOAD_URL}?{params}", token)
        if not result.get('ok'):
            print(f" FAIL ({result.get('error', '?')})")
            continue

        upload_url = result['upload_url']
        file_id = result['file_id']

        # Step 2: 파일 바이너리 업로드
        with open(file_path, 'rb') as f:
            file_bytes = f.read()

        req = urllib.request.Request(upload_url, data=file_bytes, method='POST')
        req.add_header('Content-Type', 'application/octet-stream')
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp.read()
        except Exception as e:
            print(f" FAIL ({e})")
            continue

        uploaded_files.append({'id': file_id, 'title': filename})
        print(" OK")

    if not uploaded_files:
        print("[ERROR] 업로드 성공한 파일 없음")
        return False

    # Step 3: 전체 파일을 하나의 메시지로 묶어서 채널에 공유
    complete_data = {
        'files': uploaded_files,
        'channel_id': channel_id,
    }
    if message:
        complete_data['initial_comment'] = message

    result = slack_api(SLACK_COMPLETE_URL, token, data=complete_data)

    if result.get('ok'):
        print(f"✓ Slack 일괄 업로드 완료: {len(uploaded_files)}건 → #{channel_id}")
        return True
    else:
        print(f"[ERROR] 업로드 완료 실패: {result.get('error', '?')}")
        return False


def find_report(date_str: str) -> str:
    """날짜로 보고서 파일 경로 찾기"""
    weekdays = ['월', '화', '수', '목', '금', '토', '일']
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    wd = weekdays[dt.weekday()]

    pattern = os.path.join(REPORT_DIR, f"ReNK_Daily_Report_{date_str}({wd}).docx")
    if os.path.exists(pattern):
        return pattern

    # 요일 없는 패턴도 시도
    pattern2 = os.path.join(REPORT_DIR, f"ReNK_Daily_Report_{date_str}*.docx")
    matches = glob.glob(pattern2)
    if matches:
        return matches[0]

    return ''


# ============================================================
# 테스트
# ============================================================

def test_connection():
    print("=" * 50)
    print("Slack 연결 테스트")
    print("=" * 50)

    config = load_config()
    if not config:
        return False

    token = config.get('bot_token', '')
    channel = config.get('channel_id', '')

    # auth.test로 봇 확인
    result = slack_api('https://slack.com/api/auth.test', token)
    if result.get('ok'):
        print(f"✓ Bot 인증 성공: {result.get('bot_id', '?')} ({result.get('team', '?')})")
    else:
        print(f"✗ Bot 인증 실패: {result.get('error', '?')}")
        return False

    print(f"  채널: {config.get('channel_name', channel)}")
    print("=" * 50)
    print("테스트 완료")
    return True


# ============================================================
# CLI
# ============================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Re:NK Slack 보고서 업로더')
    parser.add_argument('file', nargs='?', help='업로드할 파일 경로')
    parser.add_argument('--date', help='보고서 날짜 (YYYY-MM-DD)')
    parser.add_argument('--test', action='store_true', help='연결 테스트')
    args = parser.parse_args()

    if args.test:
        test_connection()
    elif args.date:
        config = load_config()
        if not config:
            sys.exit(1)
        token = config.get('user_token') or config.get('bot_token')
        report = find_report(args.date)
        if not report:
            print(f"[ERROR] {args.date} 보고서 파일 없음 (reports/ 폴더 확인)")
            sys.exit(1)
        upload_file_to_channel(report, config['channel_id'], token)
    elif args.file:
        config = load_config()
        if not config:
            sys.exit(1)
        token = config.get('user_token') or config.get('bot_token')
        upload_file_to_channel(args.file, config['channel_id'], token)
    else:
        print("사용법:")
        print("  python slack_uploader.py --test")
        print("  python slack_uploader.py --date 2026-04-22")
        print("  python slack_uploader.py reports/파일명.docx")
