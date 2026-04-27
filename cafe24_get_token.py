#!/usr/bin/env python3
"""
카페24 Access Token 발급 스크립트
=================================
Authorization Code → Access Token + Refresh Token 교환
"""

import urllib.request
import urllib.parse
import json
import base64
import os

# ============================================================
# 설정값
# ============================================================
CLIENT_ID = 'LzxcZZ7HMFEnzlltfgvgOE'
CLIENT_SECRET = '38aX5qPICVzrdlreBRwaqE'
MALL_ID = 'renk0'
REDIRECT_URI = 'https://www.re-nk.co.kr'

TOKEN_URL = f'https://{MALL_ID}.cafe24api.com/api/v2/oauth/token'
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'renk_cafe24_token.json')


def exchange_code(auth_code: str) -> dict:
    """Authorization Code → Access Token 교환"""
    credentials = base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()

    data = urllib.parse.urlencode({
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
    }).encode()

    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            print("\n✓ 토큰 발급 성공!")
            print(f"  Access Token: {result.get('access_token', '')[:20]}...")
            print(f"  Refresh Token: {result.get('refresh_token', '')[:20]}...")
            print(f"  만료: {result.get('expires_at', '?')}")
            print(f"  Scope: {result.get('scopes', [])}")

            # 파일 저장
            with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"\n→ 토큰 저장 완료: {TOKEN_FILE}")

            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f"\n✗ 토큰 발급 실패 (HTTP {e.code})")
        print(f"  응답: {body}")
        return {}


def refresh_token() -> dict:
    """Refresh Token으로 Access Token 갱신"""
    if not os.path.exists(TOKEN_FILE):
        print("✗ 저장된 토큰 파일 없음. 먼저 code 교환을 실행하세요.")
        return {}

    with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
        saved = json.load(f)

    rt = saved.get('refresh_token', '')
    if not rt:
        print("✗ Refresh Token이 없습니다.")
        return {}

    credentials = base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()

    data = urllib.parse.urlencode({
        'grant_type': 'refresh_token',
        'refresh_token': rt,
    }).encode()

    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={
            'Authorization': f'Basic {credentials}',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            print("\n✓ 토큰 갱신 성공!")
            print(f"  Access Token: {result.get('access_token', '')[:20]}...")
            print(f"  만료: {result.get('expires_at', '?')}")

            with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"→ 토큰 저장 완료: {TOKEN_FILE}")

            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f"\n✗ 갱신 실패 (HTTP {e.code}): {body}")
        return {}


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--refresh':
        refresh_token()
    else:
        code = input("Authorization Code 입력 (code= 뒤의 값): ").strip()
        if code:
            exchange_code(code)
        else:
            print("코드를 입력하지 않았습니다.")
