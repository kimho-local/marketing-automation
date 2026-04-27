#!/usr/bin/env python3
"""
Re:NK Google Ads API 데이터 수집기
====================================
Google Ads (P-Max, 디멘드젠) 데이터 수집 — gRPC 방식

사용법:
  python google_ads_fetcher.py                       # 어제 데이터
  python google_ads_fetcher.py --date 2026-04-16     # 특정 날짜
  python google_ads_fetcher.py --test                # API 연결 테스트

셋업 필수:
  1. pip install google-ads
  2. config/renk_google_ads_credentials.json 파일 생성
  3. Google Cloud Console → Google Ads API 활성화
"""

import os
import sys
import json
from datetime import datetime, timedelta


# ============================================================
# 설정
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, 'config', 'renk_google_ads_credentials.json')


# ============================================================
# 인증
# ============================================================

def load_credentials() -> dict:
    if not os.path.exists(CREDENTIALS_FILE):
        print("[ERROR] config/renk_google_ads_credentials.json 파일 없음.")
        return {}
    with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_client(creds: dict):
    """google-ads 클라이언트 생성"""
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError:
        print("[ERROR] google-ads 라이브러리 없음. 설치: pip install google-ads")
        return None

    config = {
        "developer_token": creds["developer_token"],
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "use_proto_plus": True,
    }
    if creds.get("login_customer_id"):
        config["login_customer_id"] = str(creds["login_customer_id"]).replace("-", "")

    return GoogleAdsClient.load_from_dict(config)


# ============================================================
# Google Ads API (gRPC) 호출
# ============================================================

def gaql_query(client, customer_id: str, query: str) -> list:
    """
    Google Ads Query Language (GAQL) 쿼리 실행 — gRPC
    """
    ga_service = client.get_service("GoogleAdsService")
    rows = []

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        for batch in response:
            for row in batch.results:
                rows.append(row)
    except Exception as e:
        print(f"[ERROR] Google Ads API: {e}")

    return rows


# ============================================================
# 데이터 수집
# ============================================================

def fetch_campaign_stats(client, customer_id: str, since: str, until: str) -> list:
    """
    캠페인별 일별 통계 수집
    반환: [{
        'date': '2026-04-16',
        'campaign_name': '...',
        'campaign_type': 'PERFORMANCE_MAX',
        'cost': 150000,
        'impressions': 25000,
        'clicks': 300,
        'conversions': 5,
        'revenue': 450000,
    }, ...]
    """
    query = f"""
        SELECT
            segments.date,
            campaign.name,
            campaign.advertising_channel_type,
            campaign.status,
            metrics.cost_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.conversions,
            metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{since}' AND '{until}'
          AND campaign.status != 'REMOVED'
          AND metrics.cost_micros > 0
        ORDER BY segments.date, campaign.name
    """

    rows = gaql_query(client, customer_id, query)
    results = []

    # 캠페인 타입 enum → 문자열 매핑
    try:
        from google.ads.googleads.enums import AdvertisingChannelTypeEnum
        type_map = {v.value: v.name for v in AdvertisingChannelTypeEnum.AdvertisingChannelType}
    except Exception:
        type_map = {}

    for row in rows:
        cost_micros = row.metrics.cost_micros
        cost = cost_micros / 1_000_000  # micros → 원

        # campaign_type: enum 값 → 문자열
        ct_enum = row.campaign.advertising_channel_type
        ct_name = type_map.get(ct_enum, str(ct_enum))

        results.append({
            'date': row.segments.date,
            'campaign_name': row.campaign.name,
            'campaign_type': ct_name,
            'cost': int(cost),
            'impressions': row.metrics.impressions,
            'clicks': row.metrics.clicks,
            'conversions': float(row.metrics.conversions),
            'revenue': int(float(row.metrics.conversions_value)),
        })

    return results


def fetch_google_data(since: str, until: str) -> dict:
    """
    Google Ads 데이터 수집 (외부 호출용)

    반환: {
        '2026-04-16': {
            'total': {'cost': ..., 'impressions': ..., 'clicks': ..., 'conversions': ..., 'revenue': ...},
            'campaigns': [ ... ],
            'by_type': {
                'P-Max': {...},
                '디멘드젠': {...},
            }
        }
    }
    """
    creds = load_credentials()
    if not creds:
        return {}

    client = get_client(creds)
    if not client:
        return {}

    customer_id = str(creds['customer_id']).replace('-', '')
    print(f"[INFO] Google Ads 데이터 수집 중 ({since} ~ {until})...")
    stats = fetch_campaign_stats(client, customer_id, since, until)

    # 일별 집계
    daily = {}
    for s in stats:
        dk = s['date']
        if dk not in daily:
            daily[dk] = {
                'total': {'cost': 0, 'impressions': 0, 'clicks': 0, 'conversions': 0, 'revenue': 0},
                'campaigns': [],
                'by_type': {},
            }

        daily[dk]['total']['cost'] += s['cost']
        daily[dk]['total']['impressions'] += s['impressions']
        daily[dk]['total']['clicks'] += s['clicks']
        daily[dk]['total']['conversions'] += s['conversions']
        daily[dk]['total']['revenue'] += s['revenue']

        daily[dk]['campaigns'].append(s)

        ct = s.get('campaign_type', '기타')
        # 한글 매핑 (enum 숫자값 + 문자열 둘 다 지원)
        type_names = {
            'PERFORMANCE_MAX': 'P-Max', '10': 'P-Max', 10: 'P-Max',
            'DEMAND_GEN': '디멘드젠', '14': '디멘드젠', 14: '디멘드젠',
            'SEARCH': '검색', '2': '검색', 2: '검색',
            'DISPLAY': '디스플레이', '6': '디스플레이', 6: '디스플레이',
            'VIDEO': '유튜브', '7': '유튜브', 7: '유튜브',
            'SHOPPING': '쇼핑', '8': '쇼핑', 8: '쇼핑',
        }
        ct_label = type_names.get(ct, str(ct))

        if ct_label not in daily[dk]['by_type']:
            daily[dk]['by_type'][ct_label] = {
                'cost': 0, 'impressions': 0, 'clicks': 0, 'conversions': 0, 'revenue': 0,
            }
        daily[dk]['by_type'][ct_label]['cost'] += s['cost']
        daily[dk]['by_type'][ct_label]['impressions'] += s['impressions']
        daily[dk]['by_type'][ct_label]['clicks'] += s['clicks']
        daily[dk]['by_type'][ct_label]['conversions'] += s['conversions']
        daily[dk]['by_type'][ct_label]['revenue'] += s['revenue']

    if daily:
        for dk in sorted(daily.keys()):
            d = daily[dk]['total']
            print(f"  {dk}: 광고비 {d['cost']:,}원 | 클릭 {d['clicks']} | 전환 {d['conversions']:.0f}")
            for tp, td in daily[dk]['by_type'].items():
                print(f"    {tp}: {td['cost']:,}원 | 클릭 {td['clicks']}")
    else:
        print("[WARN] 수집 데이터 없음")

    return daily


# ============================================================
# 테스트
# ============================================================

def test_connection():
    print("=" * 50)
    print("Google Ads API 연결 테스트 (gRPC)")
    print("=" * 50)

    creds = load_credentials()
    if not creds:
        print("✗ config/renk_google_ads_credentials.json 파일 없음")
        return False

    if not creds.get('developer_token'):
        print("✗ developer_token 없음")
        return False

    print(f"✓ 인증정보 로드 완료")
    print(f"  고객 ID: {creds.get('customer_id', '?')}")
    print(f"  MCC ID: {creds.get('login_customer_id', '없음')}")

    client = get_client(creds)
    if not client:
        return False
    print(f"✓ GoogleAdsClient 생성 성공")

    customer_id = str(creds['customer_id']).replace('-', '')
    query = "SELECT customer.id, customer.descriptive_name FROM customer LIMIT 1"
    rows = gaql_query(client, customer_id, query)

    if rows:
        row = rows[0]
        print(f"✓ 계정 연결 확인: {row.customer.descriptive_name} ({row.customer.id})")
    else:
        print("✗ 계정 조회 실패")
        return False

    print("=" * 50)
    print("테스트 완료")
    return True


# ============================================================
# CLI
# ============================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Re:NK Google Ads 데이터 수집기')
    parser.add_argument('--date', help='수집 날짜 (YYYY-MM-DD)')
    parser.add_argument('--since', help='시작일')
    parser.add_argument('--until', help='종료일')
    parser.add_argument('--test', action='store_true', help='API 연결 테스트')
    args = parser.parse_args()

    if args.test:
        test_connection()
    elif args.date:
        data = fetch_google_data(args.date, args.date)
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    elif args.since and args.until:
        data = fetch_google_data(args.since, args.until)
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        data = fetch_google_data(yesterday, yesterday)
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
