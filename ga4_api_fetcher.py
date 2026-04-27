#!/usr/bin/env python3
"""
Re:NK GA4 Data API 수집기
============================
GA4에서 일별 유입/전환/세션 데이터를 수집합니다.

사용법:
  python ga4_api_fetcher.py --test                      # API 연결 테스트
  python ga4_api_fetcher.py --date 2026-04-23           # 특정 날짜
  python ga4_api_fetcher.py --since 2026-04-22 --until 2026-04-23

수집 지표:
  - 채널별 세션/사용자 (organic, paid, direct, referral, social)
  - 전환 (purchase 이벤트)
  - 이탈률, 참여율, 평균 세션 시간
  - 신규 vs 재방문
  - 랜딩페이지 TOP 5

셋업:
  1. python ga4_auth_setup.py  (1회성 인증)
  2. config/renk_ga4_credentials.json 자동 생성 확인
"""

import os
import sys
import json
import argparse
import urllib.parse
import urllib.request
from datetime import datetime, timedelta


# ============================================================
# 설정
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GA4_CREDS_FILE = os.path.join(SCRIPT_DIR, 'config', 'renk_ga4_credentials.json')

GA4_API_BASE = 'https://analyticsdata.googleapis.com/v1beta'


# ============================================================
# 인증
# ============================================================

def load_credentials() -> dict:
    if not os.path.exists(GA4_CREDS_FILE):
        print("[ERROR] GA4 인증 파일 없음. 먼저 실행: python ga4_auth_setup.py")
        return {}
    with open(GA4_CREDS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_access_token(creds: dict) -> str:
    """refresh_token → access_token 갱신"""
    data = urllib.parse.urlencode({
        'client_id': creds['client_id'],
        'client_secret': creds['client_secret'],
        'refresh_token': creds['refresh_token'],
        'grant_type': 'refresh_token',
    }).encode('utf-8')

    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )

    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read().decode('utf-8'))
            return token_data['access_token']
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"[ERROR] access_token 갱신 실패 ({e.code}): {error_body}")
        return ''


# ============================================================
# GA4 Data API 호출
# ============================================================

def ga4_run_report(access_token: str, property_id: str, body: dict) -> dict:
    """GA4 Data API runReport 호출"""
    url = f"{GA4_API_BASE}/properties/{property_id}:runReport"

    payload = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
    )

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"[ERROR] GA4 API 호출 실패 ({e.code}): {error_body}")
        return {}


def _val(row, idx, vtype='int'):
    """GA4 응답에서 값 추출"""
    try:
        v = row['metricValues'][idx]['value']
        if vtype == 'int':
            return int(float(v))
        elif vtype == 'float':
            return round(float(v), 4)
        return v
    except (IndexError, KeyError, ValueError):
        return 0


def _dim(row, idx):
    """GA4 응답에서 차원 값 추출"""
    try:
        return row['dimensionValues'][idx]['value']
    except (IndexError, KeyError):
        return ''


# ============================================================
# 수집 함수들
# ============================================================

def fetch_overview(access_token: str, property_id: str, date_str: str) -> dict:
    """일별 전체 개요: 세션, 사용자, 신규, 전환, 매출, 이탈률 등"""
    body = {
        'dateRanges': [{'startDate': date_str, 'endDate': date_str}],
        'metrics': [
            {'name': 'sessions'},
            {'name': 'totalUsers'},
            {'name': 'newUsers'},
            {'name': 'ecommercePurchases'},
            {'name': 'purchaseRevenue'},
            {'name': 'engagementRate'},
            {'name': 'bounceRate'},
            {'name': 'averageSessionDuration'},
            {'name': 'screenPageViewsPerSession'},
        ],
    }
    result = ga4_run_report(access_token, property_id, body)
    if not result or 'rows' not in result:
        return {}

    row = result['rows'][0]
    return {
        'sessions': _val(row, 0),
        'users': _val(row, 1),
        'new_users': _val(row, 2),
        'purchases': _val(row, 3),
        'revenue': _val(row, 4),
        'engagement_rate': _val(row, 5, 'float'),
        'bounce_rate': _val(row, 6, 'float'),
        'avg_session_duration': _val(row, 7, 'float'),
        'pages_per_session': _val(row, 8, 'float'),
    }


def fetch_channels(access_token: str, property_id: str, date_str: str) -> list:
    """채널별 세션/사용자/전환"""
    body = {
        'dateRanges': [{'startDate': date_str, 'endDate': date_str}],
        'dimensions': [{'name': 'sessionDefaultChannelGroup'}],
        'metrics': [
            {'name': 'sessions'},
            {'name': 'totalUsers'},
            {'name': 'ecommercePurchases'},
            {'name': 'purchaseRevenue'},
            {'name': 'engagementRate'},
        ],
        'orderBys': [{'metric': {'metricName': 'sessions'}, 'desc': True}],
        'limit': 10,
    }
    result = ga4_run_report(access_token, property_id, body)
    if not result or 'rows' not in result:
        return []

    channels = []
    for row in result['rows']:
        channels.append({
            'channel': _dim(row, 0),
            'sessions': _val(row, 0),
            'users': _val(row, 1),
            'purchases': _val(row, 2),
            'revenue': _val(row, 3),
            'engagement_rate': _val(row, 4, 'float'),
        })
    return channels


def fetch_landing_pages(access_token: str, property_id: str, date_str: str) -> list:
    """페이지 제목 및 화면 클래스 기준 TOP 5 (조회수 기준)"""
    body = {
        'dateRanges': [{'startDate': date_str, 'endDate': date_str}],
        'dimensions': [{'name': 'pageTitle'}],
        'metrics': [
            {'name': 'screenPageViews'},
            {'name': 'totalUsers'},
            {'name': 'ecommercePurchases'},
            {'name': 'purchaseRevenue'},
            {'name': 'bounceRate'},
        ],
        'orderBys': [{'metric': {'metricName': 'screenPageViews'}, 'desc': True}],
        'limit': 5,
    }
    result = ga4_run_report(access_token, property_id, body)
    if not result or 'rows' not in result:
        return []

    pages = []
    for row in result['rows']:
        pages.append({
            'page': _dim(row, 0),
            'views': _val(row, 0),
            'users': _val(row, 1),
            'purchases': _val(row, 2),
            'revenue': _val(row, 3),
            'bounce_rate': _val(row, 4, 'float'),
        })
    return pages


def fetch_device_category(access_token: str, property_id: str, date_str: str) -> list:
    """디바이스별 세션/전환"""
    body = {
        'dateRanges': [{'startDate': date_str, 'endDate': date_str}],
        'dimensions': [{'name': 'deviceCategory'}],
        'metrics': [
            {'name': 'sessions'},
            {'name': 'totalUsers'},
            {'name': 'ecommercePurchases'},
            {'name': 'purchaseRevenue'},
        ],
        'orderBys': [{'metric': {'metricName': 'sessions'}, 'desc': True}],
    }
    result = ga4_run_report(access_token, property_id, body)
    if not result or 'rows' not in result:
        return []

    devices = []
    for row in result['rows']:
        devices.append({
            'device': _dim(row, 0),
            'sessions': _val(row, 0),
            'users': _val(row, 1),
            'purchases': _val(row, 2),
            'revenue': _val(row, 3),
        })
    return devices


def fetch_funnel_events(access_token: str, property_id: str, date_str: str) -> list:
    """고객구매여정 퍼널: 이벤트별 사용자 수 수집
    (첫 방문 → 상품조회 → 장바구니 → 결제시작 → 구매완료)
    """
    # GA4 이커머스 표준 이벤트명
    funnel_events = [
        ('session_start', '첫 방문'),
        ('view_item', '상품조회'),
        ('add_to_cart', '장바구니 담기'),
        ('begin_checkout', '결제 시작'),
        ('purchase', '구매완료'),
    ]

    body = {
        'dateRanges': [{'startDate': date_str, 'endDate': date_str}],
        'dimensions': [{'name': 'eventName'}],
        'metrics': [
            {'name': 'eventCount'},
            {'name': 'totalUsers'},
        ],
        'dimensionFilter': {
            'filter': {
                'fieldName': 'eventName',
                'inListFilter': {
                    'values': [e[0] for e in funnel_events],
                },
            },
        },
    }

    result = ga4_run_report(access_token, property_id, body)
    if not result or 'rows' not in result:
        return []

    # 이벤트명 → 수치 매핑
    event_map = {}
    for row in result['rows']:
        name = _dim(row, 0)
        event_map[name] = {
            'event_count': _val(row, 0),
            'users': _val(row, 1),
        }

    # 퍼널 순서대로 정리 + 전환율 계산
    funnel = []
    first_users = 0
    prev_users = 0
    for i, (event_name, label) in enumerate(funnel_events):
        data = event_map.get(event_name, {'event_count': 0, 'users': 0})
        users = data['users']

        if i == 0:
            first_users = users
            prev_users = users

        # 전체 대비 전환율, 이전 단계 대비 전환율
        overall_rate = (users / first_users * 100) if first_users > 0 else 0
        step_rate = (users / prev_users * 100) if prev_users > 0 else 0

        funnel.append({
            'step': i + 1,
            'event_name': event_name,
            'label': label,
            'event_count': data['event_count'],
            'users': users,
            'overall_rate': round(overall_rate, 2),
            'step_rate': round(step_rate, 2),
        })
        prev_users = users if users > 0 else prev_users

    return funnel


# ============================================================
# 통합 수집
# ============================================================

def fetch_ga4_data(since: str, until: str) -> dict:
    """
    GA4 일별 데이터 수집 (run_daily.py에서 호출)

    반환: {
        '2026-04-23': {
            'overview': { sessions, users, new_users, purchases, revenue, ... },
            'channels': [ { channel, sessions, users, purchases, revenue, ... }, ... ],
            'landing_pages': [ { page, sessions, purchases, bounce_rate }, ... ],
            'devices': [ { device, sessions, users, purchases, revenue }, ... ],
        }
    }
    """
    creds = load_credentials()
    if not creds:
        return {}

    access_token = get_access_token(creds)
    if not access_token:
        return {}

    property_id = creds.get('property_id', '526390956')

    current = datetime.strptime(since, '%Y-%m-%d')
    end = datetime.strptime(until, '%Y-%m-%d')

    daily = {}
    while current <= end:
        d = current.strftime('%Y-%m-%d')

        overview = fetch_overview(access_token, property_id, d)
        if overview:
            channels = fetch_channels(access_token, property_id, d)
            landing_pages = fetch_landing_pages(access_token, property_id, d)
            devices = fetch_device_category(access_token, property_id, d)
            funnel = fetch_funnel_events(access_token, property_id, d)

            daily[d] = {
                'overview': overview,
                'channels': channels,
                'landing_pages': landing_pages,
                'devices': devices,
                'funnel': funnel,
            }

            sessions = overview.get('sessions', 0)
            users = overview.get('users', 0)
            purchases = overview.get('purchases', 0)
            revenue = overview.get('revenue', 0)
            print(f"  {d}: 세션 {sessions:,} | 사용자 {users:,} | 구매 {purchases}건 | 매출 {revenue:,}원")

            # 채널별 요약
            for ch in channels[:5]:
                print(f"    {ch['channel']}: 세션 {ch['sessions']:,} | 구매 {ch['purchases']}건")

            # 퍼널 요약
            if funnel:
                steps = " → ".join(f"{f['label']}({f['users']:,})" for f in funnel)
                print(f"    퍼널: {steps}")
        else:
            print(f"  {d}: 데이터 없음")

        current += timedelta(days=1)

    return daily


# ============================================================
# CLI
# ============================================================

def test_connection():
    """API 연결 테스트"""
    creds = load_credentials()
    if not creds:
        return

    print("[TEST] GA4 API 연결 테스트")
    print(f"  속성 ID: {creds.get('property_id', 'N/A')}")

    access_token = get_access_token(creds)
    if not access_token:
        print("[FAIL] access_token 발급 실패")
        return

    print("  access_token 발급 OK")

    # 어제 데이터로 간단 테스트
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    overview = fetch_overview(access_token, creds.get('property_id', '526390956'), yesterday)

    if overview:
        print(f"  {yesterday} 데이터 조회 OK:")
        print(f"    세션: {overview.get('sessions', 0):,}")
        print(f"    사용자: {overview.get('users', 0):,}")
        print(f"    신규: {overview.get('new_users', 0):,}")
        print(f"    구매: {overview.get('purchases', 0)}건")
        print(f"    매출: {overview.get('revenue', 0):,}원")
        print(f"    참여율: {overview.get('engagement_rate', 0) * 100:.1f}%")
        print(f"    이탈률: {overview.get('bounce_rate', 0) * 100:.1f}%")
        print("[PASS] GA4 API 연결 성공!")
    else:
        print("[FAIL] 데이터 조회 실패")


def main():
    parser = argparse.ArgumentParser(description='Re:NK GA4 Data API 수집기')
    parser.add_argument('--test', action='store_true', help='API 연결 테스트')
    parser.add_argument('--date', help='특정 날짜 (YYYY-MM-DD)')
    parser.add_argument('--since', help='시작일')
    parser.add_argument('--until', help='종료일')
    parser.add_argument('--json', action='store_true', help='JSON 출력')
    args = parser.parse_args()

    if args.test:
        test_connection()
        return

    if args.date:
        since = until = args.date
    elif args.since and args.until:
        since, until = args.since, args.until
    else:
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        since = until = yesterday

    print(f"[INFO] GA4 데이터 수집 중 ({since} ~ {until})...")
    data = fetch_ga4_data(since, until)

    if args.json and data:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif not data:
        print("[WARN] 수집 데이터 없음")


if __name__ == '__main__':
    main()
