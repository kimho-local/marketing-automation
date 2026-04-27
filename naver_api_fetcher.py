#!/usr/bin/env python3
"""
Re:NK 네이버 광고 API 데이터 수집기
=====================================
네이버 검색광고(SA/BS/쇼검) + 성과형 디스플레이(GFA) 데이터 수집

사용법:
  python naver_api_fetcher.py                       # 어제 데이터
  python naver_api_fetcher.py --date 2026-04-16     # 특정 날짜
  python naver_api_fetcher.py --since 2026-04-01 --until 2026-04-16
  python naver_api_fetcher.py --test                # API 연결 테스트

셋업 필수:
  1. naver_credentials.json 파일 생성 (아래 형식)
  {
    "search_ad": {
      "customer_id": "네이버 검색광고 고객번호",
      "api_key": "발급받은 API Key",
      "secret_key": "발급받은 Secret Key"
    },
    "gfa": {
      "customer_id": "네이버 GFA 고객번호",
      "api_key": "발급받은 API Key",
      "secret_key": "발급받은 Secret Key"
    }
  }
  2. 네이버 검색광고 센터 → 도구 → API 관리에서 발급
"""

import os
import sys
import json
import time
import hmac
import hashlib
import base64
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta


# ============================================================
# 설정
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, 'config', 'renk_naver_credentials.json')

SEARCH_AD_BASE = 'https://api.searchad.naver.com'
GFA_BASE = 'https://api.naver.com'  # GFA API (별도 확인 필요)

# 브랜드검색 월 정액 계약 (API에서 광고비 0원 반환 → 일할계산으로 대체)
BS_MONTHLY_COST = 2_530_000  # 월 253만원

# 캠페인 유형 매핑 (네이버 검색광고)
CAMPAIGN_TYPE_MAP = {
    # 문자열 타입 (실제 API 응답)
    'WEB_SITE': '파워링크',
    'SHOPPING': '쇼핑검색',
    'BRAND_SEARCH': '브랜드검색',
    'POWER_CONTENTS': '파워컨텐츠',
    # 숫자 타입 (레거시 호환)
    '1': '파워링크',
    '2': '쇼핑검색',
    '4': '브랜드검색',
    '7': 'Performance Max',
}


# ============================================================
# 인증 헤더 생성
# ============================================================

def generate_signature(timestamp: str, method: str, uri: str, secret_key: str) -> str:
    """네이버 검색광고 API HMAC-SHA256 서명 생성"""
    message = f"{timestamp}.{method}.{uri}"
    sign = hmac.new(
        secret_key.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    return base64.b64encode(sign).decode('utf-8')


def get_auth_headers(credentials: dict, method: str, uri: str) -> dict:
    """인증 헤더 생성"""
    timestamp = str(int(time.time() * 1000))
    signature = generate_signature(
        timestamp, method, uri, credentials['secret_key']
    )
    return {
        'X-Timestamp': timestamp,
        'X-API-KEY': credentials['api_key'],
        'X-Customer': str(credentials['customer_id']),
        'X-Signature': signature,
        'Content-Type': 'application/json',
    }


# ============================================================
# 자격 증명 관리
# ============================================================

def load_credentials() -> dict:
    """naver_credentials.json 로드"""
    if not os.path.exists(CREDENTIALS_FILE):
        print("[ERROR] naver_credentials.json 파일 없음.")
        print("  → API 셋업 가이드를 참고하여 파일을 생성하세요.")
        return {}
    with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================
# 검색광고 API 호출
# ============================================================

def sa_api_get(credentials: dict, uri: str, params: dict = None) -> dict:
    """네이버 검색광고 REST API GET"""
    url = f"{SEARCH_AD_BASE}{uri}"
    if params:
        url += '?' + urllib.parse.urlencode(params)

    headers = get_auth_headers(credentials, 'GET', uri)
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f"[ERROR] 검색광고 API ({uri}, HTTP {e.code}): {body}")
        return {}
    except Exception as e:
        print(f"[ERROR] 검색광고 API 예외 ({uri}): {e}")
        return {}


def sa_api_post(credentials: dict, uri: str, body: dict) -> list:
    """네이버 검색광고 REST API POST (stat 조회용)"""
    url = f"{SEARCH_AD_BASE}{uri}"
    headers = get_auth_headers(credentials, 'POST', uri)
    data = json.dumps(body).encode('utf-8')

    req = urllib.request.Request(url, data=data, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        print(f"[ERROR] 검색광고 API POST ({uri}, HTTP {e.code}): {body_text}")
        return []
    except Exception as e:
        print(f"[ERROR] 검색광고 API POST 예외 ({uri}): {e}")
        return []


# ============================================================
# 캠페인 목록 조회
# ============================================================

def fetch_campaigns(credentials: dict) -> list:
    """전체 캠페인 목록 조회"""
    result = sa_api_get(credentials, '/ncc/campaigns')
    if isinstance(result, list):
        return result
    return result.get('campaigns', []) if isinstance(result, dict) else []


# ============================================================
# 통계 데이터 수집
# ============================================================

def fetch_campaign_stats(credentials: dict, campaign_ids: list, since: str, until: str) -> list:
    """
    캠페인별 일별 통계 조회
    /stats 엔드포인트 사용

    반환: [{
        'id': 캠페인ID,
        'stat': { 'impCnt': 노출, 'clkCnt': 클릭, 'salesAmt': 광고비, ... }
    }, ...]
    """
    # 네이버 검색광고 통계 API는 /stat/report 또는 /stats 사용
    # 날짜 형식: YYYY-MM-DD
    all_stats = []

    # 캠페인 단위 stat 조회 (최대 100개씩)
    for i in range(0, len(campaign_ids), 100):
        batch = campaign_ids[i:i+100]
        ids_str = ','.join(batch)

        result = sa_api_get(credentials, '/stats', {
            'ids': ids_str,
            'fields': '["impCnt","clkCnt","salesAmt","cpc","ctr","ccnt","crto","convAmt","ror","purchaseCcnt","purchaseConvAmt"]',
            'timeRange': json.dumps({
                'since': since,
                'until': until,
            }),
        })

        if isinstance(result, list):
            all_stats.extend(result)
        elif isinstance(result, dict) and 'data' in result:
            all_stats.extend(result['data'])

    return all_stats


def _aggregate_day_stats(credentials: dict, campaign_ids: list, campaign_map: dict, date_str: str) -> dict:
    """단일 날짜의 캠페인 통계를 집계"""
    stats = fetch_campaign_stats(credentials, campaign_ids, date_str, date_str)

    day = {
        'cost': 0, 'impressions': 0, 'clicks': 0,
        'conversions': 0, 'revenue': 0,
        'purchase_count': 0, 'purchase_revenue': 0,
        'campaigns': [],
    }

    for s in stats:
        cid = s.get('id', '')
        stat = s.get('stat', s)

        cost = stat.get('salesAmt', 0) or 0
        imp = stat.get('impCnt', 0) or 0
        clk = stat.get('clkCnt', 0) or 0
        conv = stat.get('ccnt', 0) or 0
        rev = stat.get('convAmt', 0) or 0
        p_cnt = stat.get('purchaseCcnt', 0) or 0
        p_rev = stat.get('purchaseConvAmt', 0) or 0

        day['cost'] += cost
        day['impressions'] += imp
        day['clicks'] += clk
        day['conversions'] += conv
        day['revenue'] += rev
        day['purchase_count'] += p_cnt
        day['purchase_revenue'] += p_rev

        cinfo = campaign_map.get(cid, {})
        day['campaigns'].append({
            'campaign_id': cid,
            'campaign_name': cinfo.get('name', cid),
            'campaign_type': cinfo.get('type', '기타'),
            'cost': cost, 'impressions': imp, 'clicks': clk,
            'conversions': conv, 'revenue': rev,
            'purchase_count': p_cnt, 'purchase_revenue': p_rev,
            'ctr': (clk / imp * 100) if imp > 0 else 0,
            'cpc': (cost / clk) if clk > 0 else 0,
        })

    return day


def fetch_daily_stats(credentials: dict, since: str, until: str) -> dict:
    """
    일별 통합 통계 수집 — 날짜별 개별 호출 방식

    네이버 /stats API는 timeRange 범위를 집계(합산)로만 반환하고
    일별 분리(statDt)를 제공하지 않는 경우가 많으므로,
    정확한 일별 데이터를 위해 하루씩 개별 호출한다.

    반환: {
        '2026-04-16': {
            'cost': 광고비,
            'impressions': 노출,
            'clicks': 클릭,
            'conversions': 전환수,
            'revenue': 전환매출,
            'campaigns': [
                {'name': '...', 'type': '파워링크', 'cost': ..., ...}
            ]
        }
    }
    """
    # 1. 캠페인 목록
    campaigns = fetch_campaigns(credentials)
    if not campaigns:
        print("[WARN] 캠페인 목록 조회 실패 또는 캠페인 없음")
        return {}

    active = [c for c in campaigns if c.get('status') == 'ELIGIBLE' or c.get('enable')]
    if not active:
        active = campaigns  # fallback: 전체

    campaign_map = {}
    campaign_ids = []
    for c in active:
        cid = c.get('nccCampaignId', '') or c.get('campaignId', '')
        if cid:
            campaign_ids.append(cid)
            campaign_map[cid] = {
                'name': c.get('name', ''),
                'type': CAMPAIGN_TYPE_MAP.get(str(c.get('campaignTp', '')), '기타'),
                'budget': c.get('dailyBudget', 0),
            }

    if not campaign_ids:
        return {}

    # 2. 날짜별 개별 호출
    daily = {}
    current = datetime.strptime(since, '%Y-%m-%d')
    end = datetime.strptime(until, '%Y-%m-%d')

    while current <= end:
        d = current.strftime('%Y-%m-%d')
        day = _aggregate_day_stats(credentials, campaign_ids, campaign_map, d)
        # 데이터가 있는 날만 저장 (cost > 0 또는 impressions > 0)
        if day['cost'] > 0 or day['impressions'] > 0:
            daily[d] = day
        current += timedelta(days=1)

    return daily


# ============================================================
# 통합 수집 함수 (run_daily.py에서 호출)
# ============================================================

def fetch_naver_data(since: str, until: str) -> dict:
    """
    네이버 검색광고 데이터 수집 (외부 호출용)

    반환: {
        '2026-04-16': {
            'sa': { ... 검색광고 통합 },
            'campaigns': [ ... 캠페인별 상세 ],
            'by_type': {
                '파워링크': {'cost': ..., 'clicks': ..., ...},
                '브랜드검색': {...},
                '쇼핑검색': {...},
            }
        }
    }
    """
    creds = load_credentials()
    if not creds:
        return {}

    sa_creds = creds.get('search_ad', {})
    if not sa_creds.get('api_key'):
        print("[ERROR] 네이버 검색광고 인증정보 없음")
        return {}

    print(f"[INFO] 네이버 검색광고 데이터 수집 중 ({since} ~ {until})...")
    daily_stats = fetch_daily_stats(sa_creds, since, until)

    # 캠페인 유형별 분류 + 브랜드검색 일할계산
    import calendar
    result = {}
    for date_key, data in daily_stats.items():
        by_type = {}
        for c in data.get('campaigns', []):
            ctype = c.get('campaign_type', '기타')
            if ctype not in by_type:
                by_type[ctype] = {
                    'cost': 0, 'impressions': 0, 'clicks': 0,
                    'conversions': 0, 'revenue': 0,
                    'purchase_count': 0, 'purchase_revenue': 0,
                }
            by_type[ctype]['cost'] += c.get('cost', 0)
            by_type[ctype]['impressions'] += c.get('impressions', 0)
            by_type[ctype]['clicks'] += c.get('clicks', 0)
            by_type[ctype]['conversions'] += c.get('conversions', 0)
            by_type[ctype]['revenue'] += c.get('revenue', 0)
            by_type[ctype]['purchase_count'] += c.get('purchase_count', 0)
            by_type[ctype]['purchase_revenue'] += c.get('purchase_revenue', 0)

        # 브랜드검색 일할계산: 월 정액 / 해당월 일수
        dt = datetime.strptime(date_key, '%Y-%m-%d')
        days_in_month = calendar.monthrange(dt.year, dt.month)[1]
        bs_daily_cost = round(BS_MONTHLY_COST / days_in_month)

        if '브랜드검색' not in by_type:
            by_type['브랜드검색'] = {
                'cost': 0, 'impressions': 0, 'clicks': 0,
                'conversions': 0, 'revenue': 0,
                'purchase_count': 0, 'purchase_revenue': 0,
            }
        # API 광고비가 0이면 일할계산 적용 (정액 계약이므로)
        if by_type['브랜드검색']['cost'] == 0:
            by_type['브랜드검색']['cost'] = bs_daily_cost

        # 총 광고비에도 브랜드검색 일할분 반영
        total_cost = sum(t['cost'] for t in by_type.values())

        result[date_key] = {
            'sa': {
                'cost': total_cost,
                'impressions': data['impressions'],
                'clicks': data['clicks'],
                'conversions': data['conversions'],
                'revenue': data['revenue'],
                'purchase_count': data['purchase_count'],
                'purchase_revenue': data['purchase_revenue'],
            },
            'campaigns': data['campaigns'],
            'by_type': by_type,
        }

    if result:
        for dk in sorted(result.keys()):
            d = result[dk]
            print(f"  {dk}: 광고비 {d['sa']['cost']:,}원 | 클릭 {d['sa']['clicks']} | 구매전환 {d['sa']['purchase_count']}건 | 구매매출 {d['sa']['purchase_revenue']:,}원")
            for tp, td in d['by_type'].items():
                print(f"    {tp}: {td['cost']:,}원 | 클릭 {td['clicks']} | 구매전환 {td['purchase_count']}건")
    else:
        print("[WARN] 수집 데이터 없음")

    return result


# ============================================================
# 소재(광고) 단위 수집 — Google Sheets 기입용
# ============================================================

def fetch_all_ads(credentials: dict) -> list:
    """전체 캠페인 → 광고그룹 → 소재 목록 수집"""
    campaigns = fetch_campaigns(credentials)
    if not campaigns:
        return []

    all_ads = []
    for c in campaigns:
        cid = c.get('nccCampaignId', '')
        cname = c.get('name', '')
        ctype = CAMPAIGN_TYPE_MAP.get(c.get('campaignTp', ''), '기타')

        adgroups = sa_api_get(credentials, '/ncc/adgroups', {'nccCampaignId': cid})
        if not isinstance(adgroups, list):
            continue

        for ag in adgroups:
            ads = sa_api_get(credentials, '/ncc/ads', {'nccAdgroupId': ag.get('nccAdgroupId', '')})
            if not isinstance(ads, list):
                continue

            for ad in ads:
                ad_info = ad.get('ad', {})
                mobile = ad_info.get('mobile', {})
                pc = ad_info.get('pc', {})
                url = mobile.get('display', '') or pc.get('display', '') or mobile.get('final', '') or pc.get('final', '') or ''

                all_ads.append({
                    'ad_id': ad.get('nccAdId', ''),
                    'campaign_name': cname,
                    'campaign_type': ctype,
                    'ad_type': ad.get('type', ''),
                    'url': url,
                })

    return all_ads


def fetch_ad_stats(credentials: dict, ad_ids: list, date_str: str) -> dict:
    """소재 ID 목록 → 일별 통계 배치 조회"""
    stats = {}
    for i in range(0, len(ad_ids), 100):
        batch = ad_ids[i:i+100]
        ids_str = ','.join(batch)
        r = sa_api_get(credentials, '/stats', {
            'ids': ids_str,
            'fields': '["impCnt","clkCnt","salesAmt","purchaseCcnt","purchaseConvAmt"]',
            'timeRange': json.dumps({'since': date_str, 'until': date_str}),
        })
        if r and 'data' in r:
            for item in r['data']:
                stats[item.get('id', '')] = item
    return stats


def fetch_naver_ad_rows(date_str: str) -> list:
    """
    소재 단위 일별 데이터 수집 → Google Sheets 행 리스트 반환

    반환: [{
        'campaign_name': '캠페인명',
        'campaign_type': '파워링크',
        'ad_id': 'nad-...',
        'ad_type': 'TEXT_45',
        'url': 'https://...',
        'date': '2026-04-21',
        'impressions': 100,
        'clicks': 5,
        'cost': 1000,
        'purchase_count': 1,
        'purchase_revenue': 50000,
    }, ...]
    """
    creds = load_credentials()
    if not creds:
        return []

    sa_creds = creds.get('search_ad', {})
    if not sa_creds.get('api_key'):
        print("[ERROR] 네이버 검색광고 인증정보 없음")
        return []

    print(f"[INFO] 네이버 SA 소재 단위 수집 중 ({date_str})...")

    # 1. 전체 소재 목록
    all_ads = fetch_all_ads(sa_creds)
    if not all_ads:
        print("[WARN] 소재 없음")
        return []
    print(f"  소재 {len(all_ads)}개 수집 완료")

    # 2. 통계 배치 조회
    ad_ids = [a['ad_id'] for a in all_ads]
    stats = fetch_ad_stats(sa_creds, ad_ids, date_str)
    print(f"  통계 {len(stats)}개 조회")

    # 3. 병합 (노출 > 0만)
    rows = []
    for ad in all_ads:
        stat = stats.get(ad['ad_id'])
        if not stat:
            continue
        imp = stat.get('impCnt', 0) or 0
        clk = stat.get('clkCnt', 0) or 0
        cost = stat.get('salesAmt', 0) or 0
        p_cnt = stat.get('purchaseCcnt', 0) or 0
        p_rev = stat.get('purchaseConvAmt', 0) or 0
        # 노출/클릭/비용/전환 모두 0이면 제외
        if imp == 0 and clk == 0 and cost == 0 and p_cnt == 0:
            continue

        rows.append({
            'campaign_name': ad['campaign_name'],
            'campaign_type': ad['campaign_type'],
            'ad_id': ad['ad_id'],
            'ad_type': ad['ad_type'],
            'url': ad['url'],
            'date': date_str,
            'impressions': imp,
            'clicks': clk,
            'cost': cost,
            'purchase_count': p_cnt,
            'purchase_revenue': p_rev,
        })

    print(f"  활성 소재 {len(rows)}개")
    return rows


# ============================================================
# 테스트
# ============================================================

def test_connection():
    """네이버 검색광고 API 연결 테스트"""
    print("=" * 50)
    print("네이버 검색광고 API 연결 테스트")
    print("=" * 50)

    creds = load_credentials()
    if not creds:
        print("✗ naver_credentials.json 파일 없음")
        return False

    sa_creds = creds.get('search_ad', {})
    if not sa_creds.get('api_key'):
        print("✗ 검색광고 인증정보 없음")
        return False

    print(f"✓ 인증정보 로드 완료")
    print(f"  고객번호: {sa_creds.get('customer_id', '?')}")

    # 캠페인 목록 조회
    campaigns = fetch_campaigns(sa_creds)
    if campaigns:
        print(f"✓ 캠페인 {len(campaigns)}개 조회 성공")
        for c in campaigns[:5]:
            tp = CAMPAIGN_TYPE_MAP.get(str(c.get('campaignTp', '')), '기타')
            print(f"  - [{tp}] {c.get('name', '?')}")
    else:
        print("✗ 캠페인 조회 실패")
        return False

    print("=" * 50)
    print("테스트 완료")
    return True


# ============================================================
# CLI
# ============================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Re:NK 네이버 광고 데이터 수집기')
    parser.add_argument('--date', help='수집 날짜 (YYYY-MM-DD)')
    parser.add_argument('--since', help='시작일')
    parser.add_argument('--until', help='종료일')
    parser.add_argument('--test', action='store_true', help='API 연결 테스트')
    args = parser.parse_args()

    if args.test:
        test_connection()
    elif args.date:
        data = fetch_naver_data(args.date, args.date)
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    elif args.since and args.until:
        data = fetch_naver_data(args.since, args.until)
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        data = fetch_naver_data(yesterday, yesterday)
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
