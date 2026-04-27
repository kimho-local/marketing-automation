#!/usr/bin/env python3
"""
GA4 API OAuth2 인증 셋업 (1회성)
=================================
기존 Google Ads OAuth2 앱과 동일한 client_id/client_secret을 사용하되,
GA4 Analytics Data API scope를 추가하여 새 refresh_token을 발급받습니다.

사용법:
  python ga4_auth_setup.py

실행 후:
  1. 브라우저가 자동으로 열림
  2. Google 계정으로 로그인 → 권한 승인
  3. 승인 완료 → 자동으로 인증 코드 수신
  4. config/renk_ga4_credentials.json 자동 생성
"""

import os
import sys
import json
import webbrowser
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(SCRIPT_DIR, 'config')

# Google Ads 인증 파일에서 client_id/client_secret 가져오기
ADS_CREDS_FILE = os.path.join(CONFIG_DIR, 'renk_google_ads_credentials.json')
GA4_CREDS_FILE = os.path.join(CONFIG_DIR, 'renk_ga4_credentials.json')

GA4_PROPERTY_ID = '526390956'
SCOPES = 'https://www.googleapis.com/auth/analytics.readonly'
REDIRECT_PORT = 8085
REDIRECT_URI = f'http://localhost:{REDIRECT_PORT}'


# ── 로컬 HTTP 서버 (인증 코드 수신용) ──

auth_code_result = {'code': None, 'error': None}


class AuthHandler(BaseHTTPRequestHandler):
    """OAuth2 리다이렉트를 받아 인증 코드를 추출"""

    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        if 'code' in query:
            auth_code_result['code'] = query['code'][0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(
                '<html><body style="font-family:sans-serif;text-align:center;padding:60px">'
                '<h2>✅ GA4 인증 완료!</h2>'
                '<p>이 창을 닫고 터미널로 돌아가세요.</p>'
                '</body></html>'.encode('utf-8')
            )
        elif 'error' in query:
            auth_code_result['error'] = query['error'][0]
            self.send_response(400)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(
                f'<html><body style="font-family:sans-serif;text-align:center;padding:60px">'
                f'<h2>❌ 인증 실패</h2>'
                f'<p>오류: {query["error"][0]}</p>'
                f'</body></html>'.encode('utf-8')
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # 서버 로그 숨김


def load_ads_creds():
    if not os.path.exists(ADS_CREDS_FILE):
        print(f"[ERROR] Google Ads 인증 파일 없음: {ADS_CREDS_FILE}")
        sys.exit(1)
    with open(ADS_CREDS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_auth_url(client_id):
    params = {
        'client_id': client_id,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPES,
        'response_type': 'code',
        'access_type': 'offline',
        'prompt': 'consent',
    }
    base = 'https://accounts.google.com/o/oauth2/v2/auth'
    return f"{base}?{urllib.parse.urlencode(params)}"


def exchange_code(client_id, client_secret, auth_code):
    """인증 코드 → refresh_token + access_token 교환"""
    data = urllib.parse.urlencode({
        'code': auth_code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code',
    }).encode('utf-8')

    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"[ERROR] 토큰 교환 실패 ({e.code}): {error_body}")
        sys.exit(1)


def main():
    ads_creds = load_ads_creds()
    client_id = ads_creds['client_id']
    client_secret = ads_creds['client_secret']

    print("=" * 60)
    print("  GA4 API OAuth2 인증 셋업")
    print("=" * 60)
    print()

    # 로컬 HTTP 서버 시작
    try:
        server = HTTPServer(('localhost', REDIRECT_PORT), AuthHandler)
    except OSError:
        print(f"[ERROR] 포트 {REDIRECT_PORT} 사용 중. 다른 프로그램을 종료하거나 잠시 후 재시도하세요.")
        sys.exit(1)

    auth_url = get_auth_url(client_id)

    print("브라우저에서 Google 계정 승인 페이지를 엽니다...")
    print()
    print("브라우저가 자동으로 열리지 않으면 아래 URL을 수동으로 복사/붙여넣기:")
    print(auth_url)
    print()

    # 브라우저 자동 열기
    webbrowser.open(auth_url)

    print("승인 대기 중... (브라우저에서 승인해주세요)")

    # 인증 코드 수신 대기 (1회만)
    server.handle_request()
    server.server_close()

    if auth_code_result['error']:
        print(f"\n[ERROR] 인증 거부됨: {auth_code_result['error']}")
        sys.exit(1)

    if not auth_code_result['code']:
        print("\n[ERROR] 인증 코드를 받지 못했습니다.")
        sys.exit(1)

    print("\n인증 코드 수신 완료! 토큰 교환 중...")
    token_data = exchange_code(client_id, client_secret, auth_code_result['code'])

    # GA4 인증 파일 저장
    ga4_creds = {
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': token_data['refresh_token'],
        'property_id': GA4_PROPERTY_ID,
    }

    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(GA4_CREDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(ga4_creds, f, indent=2, ensure_ascii=False)

    print()
    print("=" * 60)
    print(f"  GA4 인증 완료!")
    print(f"  저장: {GA4_CREDS_FILE}")
    print(f"  GA4 속성 ID: {GA4_PROPERTY_ID}")
    print("=" * 60)
    print()
    print("이제 ga4_api_fetcher.py를 실행할 수 있습니다:")
    print("  python ga4_api_fetcher.py --test")


if __name__ == '__main__':
    main()
