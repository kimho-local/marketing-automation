#!/usr/bin/env python3
"""
Re:NK META API 데이터 자동 수집기
====================================
발렌라이프 비즈니스 포트폴리오 > 리엔케이 클라이언트 계정
- 스마트스토어 광고계정: act_886230967162493
- 자사몰 광고계정:      act_901839975672999

Meta Graph API v21.0 사용
필수 조건: ads_read 권한의 시스템 유저 토큰

사용법:
  # 어제 데이터 자동 수집 + 리포트 기입
  python meta_api_fetcher.py --report-csv "리포트.csv"

  # 특정 날짜 수집
  python meta_api_fetcher.py --date 2026-03-29 --report-csv "리포트.csv"

  # 날짜 범위 수집
  python meta_api_fetcher.py --since 2026-03-01 --until 2026-03-29 --report-csv "리포트.csv"

  # API 연결 테스트만 실행
  python meta_api_fetcher.py --test

  # CSV 저장만 (리포트 미기입)
  python meta_api_fetcher.py --date 2026-03-29 --save-csv-only
"""

import os
import sys
import csv
import json
import time
import argparse
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# 설정값 (환경변수 또는 직접 입력)
# ============================================================

CONFIG = {
    # Meta API 설정
    'API_VERSION': 'v21.0',
    'BASE_URL': 'https://graph.facebook.com',

    # 광고계정 ID
    'ACCOUNT_SS': 'act_886230967162493',    # 스마트스토어
    'ACCOUNT_OWN': 'act_901839975672999',   # 자사몰

    # 액세스 토큰 (환경변수 META_ACCESS_TOKEN 우선 사용)
    'ACCESS_TOKEN': os.environ.get('META_ACCESS_TOKEN', ''),

    # 데이터 필드
    'FIELDS': ','.join([
        'spend',                              # 광고비
        'impressions',                        # 노출수
        'inline_link_clicks',                 # 링크 클릭
        'actions',                            # 구매 등 전환
        'action_values',                      # 구매 전환값(매출) — 자사몰 픽셀
        'catalog_segment_actions',            # 협력광고 공유항목 전환 (결과)
        'catalog_segment_value',              # 협력광고 공유항목 구매 전환값
        'video_thruplay_watched_actions',     # 동영상 조회(ThruPlay)
    ]),

    # CSV 저장 경로 (스크립트 위치 기준)
    'CSV_OUTPUT_DIR': os.path.dirname(os.path.abspath(__file__)),
}

# 토큰 하드코딩 (환경변수 미설정 시 fallback)
# 보안 주의: 실제 운영 시 환경변수 META_ACCESS_TOKEN 사용 권장
_FALLBACK_TOKEN = (
    'EAAMYYcHPWEoBROLmC1z6TXBJ40j8SgHuS2NfuLFiKqzZCwZAEOZC6WcXZCfxH73'
    'ZBuPjtjv7mZAoYwncmRYqMIO5H4sUsTHmlMnZB5s5ZCdnLyCRB6hUk9X2zRPXyGqIG'
    'UELFgEQhE45e5tPMbAlN0muHA9NphZC6NYSzqHOXWWRFyILg6rlpbbHbnlGfkajxOQZDZD'
)

if not CONFIG['ACCESS_TOKEN']:
    CONFIG['ACCESS_TOKEN'] = _FALLBACK_TOKEN


# ============================================================
# API 호출 유틸리티
# ============================================================

def api_get(endpoint: str, params: dict, retry: int = 3) -> dict:
    """
    Meta Graph API GET 요청 (urllib 사용, requests 불필요)

    Args:
        endpoint: /v21.0/act_xxx/insights 형태
        params: 쿼리 파라미터
        retry: 재시도 횟수

    Returns:
        API 응답 dict
    """
    params['access_token'] = CONFIG['ACCESS_TOKEN']
    url = f"{CONFIG['BASE_URL']}{endpoint}?{urllib.parse.urlencode(params)}"

    for attempt in range(retry):
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'ReNK-Cowork-Automation/1.0'}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode('utf-8')
                return json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            error_data = {}
            try:
                error_data = json.loads(body)
            except Exception:
                pass

            error_msg = error_data.get('error', {})
            code = error_msg.get('code', e.code)
            msg = error_msg.get('message', str(e))

            # 토큰 만료
            if code in [190, 102, 104]:
                print(f"\n[오류] 액세스 토큰이 만료되었습니다 (code: {code})")
                print("  → META_API_셋업가이드.html을 참고하여 토큰을 재발급하세요.")
                sys.exit(1)

            # 권한 없음
            if code in [200, 273, 10]:
                print(f"\n[오류] 권한 부족 (code: {code}): {msg}")
                print("  → System User에 ads_read 권한이 있는지 확인하세요.")
                sys.exit(1)

            # Rate limit
            if code in [4, 17, 32]:
                wait = 60 * (attempt + 1)
                print(f"  [재시도 {attempt+1}/{retry}] Rate limit → {wait}초 대기...")
                time.sleep(wait)
                continue

            print(f"  [HTTP 오류 {e.code}] {msg}")
            if attempt < retry - 1:
                time.sleep(5)
                continue
            raise

        except urllib.error.URLError as e:
            print(f"  [연결 오류] {e.reason}")
            if attempt < retry - 1:
                print(f"  → {5*(attempt+1)}초 후 재시도...")
                time.sleep(5 * (attempt + 1))
                continue
            raise

    return {}


def get_all_pages(endpoint: str, params: dict) -> list:
    """페이지네이션 처리하여 전체 데이터 수집"""
    all_data = []
    response = api_get(endpoint, params)

    while response:
        data = response.get('data', [])
        all_data.extend(data)

        # 다음 페이지 확인
        paging = response.get('paging', {})
        next_url = paging.get('next')
        if not next_url or not data:
            break

        # 다음 페이지 파라미터 추출
        parsed = urllib.parse.urlparse(next_url)
        next_params = dict(urllib.parse.parse_qsl(parsed.query))
        response = api_get(endpoint, next_params)

    return all_data


# ============================================================
# Meta Insights 데이터 파싱
# ============================================================

def parse_insights_row(row: dict) -> dict:
    """
    API 응답 단일 행을 내부 포맷으로 변환

    Meta API actions 배열 구조:
    [{"action_type": "purchase", "value": "5"}, ...]
    """
    def get_action(actions_list, action_type):
        if not actions_list:
            return 0
        for a in actions_list:
            if a.get('action_type') == action_type:
                try:
                    return float(a.get('value', 0))
                except (ValueError, TypeError):
                    return 0
        return 0

    # 구매 action_type 우선순위 (첫 번째 매칭값만 사용 — 중복 합산 방지)
    # Meta API는 동일 전환을 purchase / offsite_conversion / omni_purchase 등
    # 여러 action_type에 중복 기록하므로, 합산하면 2~3배 뻥튀기됨.
    # → 우선순위 순서대로 탐색하여 첫 번째 값만 채택한다.
    purchase_priority = [
        'purchase',                                         # 자사몰 픽셀 기본
        'omni_purchase',                                    # 협력 광고 포함 통합 구매
        'offsite_conversion.fb_pixel_purchase',             # 픽셀 오프사이트 전환
        'app_custom_event.fb_mobile_purchase',              # 앱 구매
        'collaborative_ads_shared_catalog_purchase',        # 협력 광고 구매 (구형)
    ]

    actions = row.get('actions', [])
    action_values = row.get('action_values', [])
    catalog_segment_actions = row.get('catalog_segment_actions', [])
    catalog_segment_value = row.get('catalog_segment_value', [])
    thruplay = row.get('video_thruplay_watched_actions', [])

    # 구매 건수 — 우선순위 첫 매칭
    purchases = 0
    for t in purchase_priority:
        val = get_action(actions, t)
        if val > 0:
            purchases = val
            break

    # 구매 전환값(매출) — 우선순위 첫 매칭
    revenue = 0
    for t in purchase_priority:
        val = get_action(action_values, t)
        if val > 0:
            revenue = val
            break

    # 랜딩페이지 조회
    landing_page_views = get_action(actions, 'landing_page_view')

    # 웹사이트 콘텐츠 조회 — 우선순위 첫 매칭
    content_view_types = [
        'view_content',
        'offsite_conversion.fb_pixel_view_content',
    ]
    content_views = 0
    for t in content_view_types:
        val = get_action(actions, t)
        if val > 0:
            content_views = val
            break

    # ── 협력광고(CPAS) 공유항목 전환 데이터 ──
    # 대시보드: '공유 항목의 구매 전환값' / '결과(구매)' / '공유 항목의 구매 ROAS'
    # API: catalog_segment_actions / catalog_segment_value
    cpas_purchase_types = [
        'purchase',
        'omni_purchase',
    ]
    cpas_purchases = 0
    for t in cpas_purchase_types:
        val = get_action(catalog_segment_actions or [], t)
        if val > 0:
            cpas_purchases = val
            break

    cpas_revenue = 0
    for t in cpas_purchase_types:
        val = get_action(catalog_segment_value or [], t)
        if val > 0:
            cpas_revenue = val
            break

    # ThruPlay 합산 (여러 액션 타입 가능)
    views = 0
    if isinstance(thruplay, list):
        for tp in thruplay:
            try:
                views += float(tp.get('value', 0))
            except (ValueError, TypeError):
                pass
    elif isinstance(thruplay, (int, float)):
        views = float(thruplay)

    return {
        'date': row.get('date_start', ''),
        'cost': float(row.get('spend', 0)),
        'impressions': float(row.get('impressions', 0)),
        'clicks': float(row.get('inline_link_clicks', 0)),
        'purchases': purchases,
        'revenue': revenue,
        'cpas_purchases': cpas_purchases,      # 공유항목 구매 건수
        'cpas_revenue': cpas_revenue,          # 공유항목 구매 전환값
        'views': views,
        'landing_page_views': landing_page_views,
        'content_views': content_views,
    }


# ============================================================
# 계정별 인사이트 수집
# ============================================================

def fetch_account_insights(account_id: str, since: str, until: str, label: str = '') -> dict:
    """
    광고계정의 일별 인사이트 데이터 수집

    Args:
        account_id: 광고계정 ID (예: act_886230967162493)
        since: 시작일 (YYYY-MM-DD)
        until: 종료일 (YYYY-MM-DD)
        label: 로그용 레이블

    Returns:
        dict: {날짜: {cost, revenue, impressions, clicks, views, purchases}}
    """
    print(f"\n[{label or account_id}] 데이터 수집 중... ({since} ~ {until})")

    endpoint = f"/{CONFIG['API_VERSION']}/{account_id}/insights"
    params = {
        'fields': CONFIG['FIELDS'],
        'time_range': json.dumps({'since': since, 'until': until}),
        'time_increment': '1',     # 일별 분리
        'level': 'account',        # 계정 레벨 집계
        'limit': '100',
    }

    rows = get_all_pages(endpoint, params)

    if not rows:
        print(f"  → 해당 기간 데이터 없음 (광고 집행 없거나 권한 확인 필요)")
        return {}

    daily_data = {}
    for row in rows:
        parsed = parse_insights_row(row)
        date_key = parsed['date']
        if date_key:
            # 같은 날짜 중복 시 합산 (페이지네이션 중복 방지)
            ALL_KEYS = ['cost', 'revenue', 'impressions', 'clicks', 'views',
                        'purchases', 'landing_page_views', 'content_views',
                        'cpas_purchases', 'cpas_revenue']
            if date_key in daily_data:
                for k in ALL_KEYS:
                    daily_data[date_key][k] += parsed.get(k, 0)
            else:
                daily_data[date_key] = {k: parsed.get(k, 0) for k in ALL_KEYS}

    total_cost = sum(v['cost'] for v in daily_data.values())
    total_rev = sum(v['revenue'] for v in daily_data.values())
    total_cpas = sum(v.get('cpas_revenue', 0) for v in daily_data.values())
    rev_label = f"총 매출: {int(total_rev):,}원"
    if total_cpas > 0:
        rev_label += f" | 공유항목 구매전환값: {int(total_cpas):,}원"
    print(f"  → {len(daily_data)}일 수집 완료 | 총 광고비: {int(total_cost):,}원 | {rev_label}")

    return daily_data


# ============================================================
# 캠페인별 인사이트 수집 (level=campaign)
# ============================================================

def fetch_campaign_insights(account_id: str, since: str, until: str, label: str = '') -> dict:
    """
    광고계정의 캠페인별 일별 인사이트 수집

    Args:
        account_id: 광고계정 ID
        since / until: 날짜 범위

    Returns:
        dict: {날짜: [{campaign_name, cost, impressions, clicks, purchases, revenue, views}, ...]}
    """
    print(f"\n[{label or account_id}] 캠페인별 데이터 수집 중... ({since} ~ {until})")

    endpoint = f"/{CONFIG['API_VERSION']}/{account_id}/insights"
    params = {
        'fields': CONFIG['FIELDS'] + ',campaign_name,campaign_id',
        'time_range': json.dumps({'since': since, 'until': until}),
        'time_increment': '1',
        'level': 'campaign',
        'limit': '500',
    }

    rows = get_all_pages(endpoint, params)

    if not rows:
        print(f"  → 해당 기간 캠페인 데이터 없음")
        return {}

    daily_campaigns = {}
    for row in rows:
        parsed = parse_insights_row(row)
        date_key = parsed['date']
        parsed['campaign_name'] = row.get('campaign_name', '(이름 없음)')

        if date_key not in daily_campaigns:
            daily_campaigns[date_key] = []
        daily_campaigns[date_key].append(parsed)

    # 지출 기준 내림차순 정렬
    for date_key in daily_campaigns:
        daily_campaigns[date_key].sort(key=lambda x: x.get('cost', 0), reverse=True)

    total = sum(len(v) for v in daily_campaigns.values())
    print(f"  → {len(daily_campaigns)}일 × {total}건 캠페인 수집 완료")

    return daily_campaigns


# ============================================================
# API 연결 테스트
# ============================================================

def test_connection():
    """토큰 유효성 및 계정 접근 권한 테스트"""
    print("=" * 60)
    print("Meta API 연결 테스트")
    print("=" * 60)

    # 1. 토큰 유효성 확인
    print("\n[1] 토큰 유효성 확인...")
    try:
        me = api_get(f"/{CONFIG['API_VERSION']}/me", {'fields': 'id,name'})
        print(f"  ✓ 토큰 유효 | 사용자: {me.get('name', '?')} (ID: {me.get('id', '?')})")
    except Exception as e:
        print(f"  ✗ 토큰 무효: {e}")
        return False

    # 2. 계정 접근 권한 확인
    accounts_to_test = [
        (CONFIG['ACCOUNT_SS'], '스마트스토어'),
        (CONFIG['ACCOUNT_OWN'], '자사몰'),
    ]

    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    for account_id, label in accounts_to_test:
        print(f"\n[2] {label} 계정 접근 테스트 ({account_id})...")
        try:
            endpoint = f"/{CONFIG['API_VERSION']}/{account_id}/insights"
            params = {
                'fields': 'spend,impressions',
                'date_preset': 'yesterday',
                'level': 'account',
                'limit': '1',
            }
            result = api_get(endpoint, params)
            data = result.get('data', [])
            if data:
                spend = data[0].get('spend', 0)
                impr = data[0].get('impressions', 0)
                print(f"  ✓ 접근 가능 | 어제 광고비: {float(spend):,.0f}원 | 노출: {float(impr):,.0f}회")
            else:
                print(f"  ✓ 접근 가능 (어제 집행 데이터 없음)")
        except Exception as e:
            print(f"  ✗ 접근 실패: {e}")

    print("\n" + "=" * 60)
    print("테스트 완료")
    print("=" * 60)
    return True


# ============================================================
# CSV 저장 (meta_processor.py 호환 포맷)
# ============================================================

def save_to_csv(daily_data: dict, filename: str) -> str:
    """
    수집된 데이터를 meta_processor.py 호환 CSV로 저장

    Args:
        daily_data: {날짜: {cost, revenue, ...}} dict
        filename: 저장 파일명

    Returns:
        저장된 파일 경로
    """
    filepath = os.path.join(CONFIG['CSV_OUTPUT_DIR'], filename)
    with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['날짜', '캠페인 이름', '비용', '노출수', '링크 클릭', '구매', '구매 전환값', '동영상 조회'])
        for date_key in sorted(daily_data.keys()):
            d = daily_data[date_key]
            writer.writerow([
                date_key,
                'API_자동수집',
                int(d.get('cost', 0)),
                int(d.get('impressions', 0)),
                int(d.get('clicks', 0)),
                int(d.get('purchases', 0)),
                int(d.get('revenue', 0)),
                int(d.get('views', 0)),
            ])
    print(f"  → CSV 저장: {filepath}")
    return filepath


# ============================================================
# 메인 실행
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='Re:NK META API 데이터 수집 → 커머스 리포트 자동 기입',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 어제 데이터 자동 수집 + 리포트 기입
  python meta_api_fetcher.py --report-csv "리엔케이 리포트.csv"

  # 특정 날짜
  python meta_api_fetcher.py --date 2026-03-29 --report-csv "리포트.csv"

  # 날짜 범위
  python meta_api_fetcher.py --since 2026-03-01 --until 2026-03-29 --report-csv "리포트.csv"

  # API 연결 테스트
  python meta_api_fetcher.py --test

  # 토큰을 환경변수로 설정 (권장)
  set META_ACCESS_TOKEN=EAAM...  (Windows)
  export META_ACCESS_TOKEN=EAAM...  (Mac/Linux)
        """
    )

    parser.add_argument('--test', action='store_true', help='API 연결 테스트만 실행')
    parser.add_argument('--date', help='수집 날짜 (YYYY-MM-DD). 미지정시 어제')
    parser.add_argument('--since', help='수집 시작일 (YYYY-MM-DD)')
    parser.add_argument('--until', help='수집 종료일 (YYYY-MM-DD)')
    parser.add_argument('--report-csv', help='기입할 리포트 CSV 경로')
    parser.add_argument('--output', help='출력 리포트 경로 (미지정시 원본 덮어쓰기)')
    parser.add_argument('--save-csv-only', action='store_true', help='리포트 기입 없이 CSV만 저장')
    parser.add_argument('--token', help='액세스 토큰 (환경변수 META_ACCESS_TOKEN 우선)')

    args = parser.parse_args()

    # 토큰 override
    if args.token:
        CONFIG['ACCESS_TOKEN'] = args.token

    if not CONFIG['ACCESS_TOKEN']:
        print("[오류] META_ACCESS_TOKEN 환경변수 또는 --token 인수가 필요합니다.")
        sys.exit(1)

    # 연결 테스트 모드
    if args.test:
        test_connection()
        return

    # 날짜 범위 결정
    if args.date:
        since = until = args.date
    elif args.since and args.until:
        since = args.since
        until = args.until
    else:
        # 기본: 어제
        yesterday = datetime.now() - timedelta(days=1)
        since = until = yesterday.strftime('%Y-%m-%d')

    print(f"\n{'='*60}")
    print(f"Re:NK META 광고 데이터 수집")
    print(f"기간: {since} ~ {until}")
    print(f"{'='*60}")

    # 1. 스마트스토어 데이터 수집
    ss_data = fetch_account_insights(
        CONFIG['ACCOUNT_SS'], since, until, '스마트스토어'
    )

    # 2. 자사몰 데이터 수집
    own_data = fetch_account_insights(
        CONFIG['ACCOUNT_OWN'], since, until, '자사몰'
    )

    if not ss_data and not own_data:
        print("\n[경고] 수집된 데이터가 없습니다.")
        sys.exit(0)

    # 3. CSV 저장 (항상 저장)
    today_str = datetime.now().strftime('%Y%m%d')
    ss_csv_path = None
    own_csv_path = None

    if ss_data:
        ss_csv_path = save_to_csv(ss_data, f"meta_ss_{today_str}.csv")
    if own_data:
        own_csv_path = save_to_csv(own_data, f"meta_own_{today_str}.csv")

    # 4. 리포트 기입
    if args.save_csv_only:
        print("\n[완료] --save-csv-only 모드: 리포트 기입을 건너뜁니다.")
        return

    if not args.report_csv:
        print("\n[완료] --report-csv 미지정: CSV만 저장되었습니다.")
        print(f"  리포트 기입을 원하면 --report-csv '파일경로.csv' 를 추가하세요.")
        return

    if not os.path.exists(args.report_csv):
        print(f"\n[오류] 리포트 파일을 찾을 수 없습니다: {args.report_csv}")
        sys.exit(1)

    # meta_processor.py의 update_report 호출
    print(f"\n[4] 리포트 기입 시작: {args.report_csv}")
    try:
        # 같은 디렉터리의 meta_processor 임포트
        script_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, script_dir)
        from meta_processor import update_report, validate_data

        if ss_data:
            validate_data(ss_data, "스마트스토어")
        if own_data:
            validate_data(own_data, "자사몰")

        updated = update_report(
            args.report_csv,
            ss_data or {},
            own_data or {},
            args.output
        )

        if updated:
            print(f"\n✓ {len(updated)}일 데이터 기입 완료: {', '.join(sorted(updated))}")
        else:
            print("\n[경고] 리포트에 일치하는 날짜 행이 없습니다.")
            print("  → 리포트 CSV의 일별 데이터 섹션에 해당 날짜 행이 있는지 확인하세요.")

    except ImportError:
        print("\n[오류] meta_processor.py를 찾을 수 없습니다.")
        print(f"  → {script_dir}/meta_processor.py 가 존재하는지 확인하세요.")
        sys.exit(1)


if __name__ == '__main__':
    main()
