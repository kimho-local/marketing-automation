#!/usr/bin/env python3
"""Slack 봇이 올린 파일 조회/삭제"""
import os, sys, json, urllib.request, urllib.error

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(SCRIPT_DIR, 'config', 'renk_slack_config.json'), 'r', encoding='utf-8') as f:
    config = json.load(f)

TOKEN = config['bot_token']
CHANNEL = config['channel_id']

def api_call(method, params=None, post_data=None):
    url = f"https://slack.com/api/{method}"
    if params:
        url += '?' + urllib.parse.urlencode(params)
    headers = {'Authorization': f'Bearer {TOKEN}'}
    if post_data:
        headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(url, data=json.dumps(post_data).encode(), headers=headers)
    else:
        req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f"[ERROR] {method} (HTTP {e.code}): {body[:200]}")
        return {'ok': False, 'error': str(e.code)}

if __name__ == '__main__':
    import urllib.parse

    if len(sys.argv) > 1 and sys.argv[1] == '--delete-all':
        # 봇이 올린 파일 전체 삭제
        result = api_call('files.list', {'channel': CHANNEL, 'count': 20})
        if not result.get('ok'):
            print(f"파일 목록 조회 실패: {result.get('error')}")
            sys.exit(1)
        files = result.get('files', [])
        if not files:
            print("삭제할 파일 없음")
            sys.exit(0)
        for f in files:
            r = api_call('files.delete', post_data={'file': f['id']})
            status = '✓ 삭제' if r.get('ok') else f'✗ 실패({r.get("error")})'
            print(f"  {status}: {f['name']}")

    elif len(sys.argv) > 1 and sys.argv[1].startswith('F'):
        # 특정 파일 ID 삭제
        r = api_call('files.delete', post_data={'file': sys.argv[1]})
        print('✓ 삭제 완료' if r.get('ok') else f'✗ 실패: {r.get("error")}')

    else:
        # 파일 목록 조회
        result = api_call('files.list', {'channel': CHANNEL, 'count': 10})
        if not result.get('ok'):
            print(f"파일 목록 조회 실패: {result.get('error')}")
            print("→ files:read scope 추가 후 Reinstall 필요")
            sys.exit(1)
        files = result.get('files', [])
        if not files:
            print("파일 없음")
        else:
            print(f"최근 파일 {len(files)}개:")
            for f in files:
                from datetime import datetime
                ts = datetime.fromtimestamp(f['created']).strftime('%m/%d %H:%M')
                print(f"  {f['id']} | {f['name']} | {ts}")
            print(f"\n전체 삭제: python slack_file_cleanup.py --delete-all")
            print(f"개별 삭제: python slack_file_cleanup.py F파일ID")
