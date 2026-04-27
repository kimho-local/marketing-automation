#!/usr/bin/env python3
"""
Re:NK 일간 통합 자동화 실행기 v3
==================================
매일 아침 1회 실행 → 전체 매체 데이터 수집 → Google Sheets 아카이빙 → docx 보고서 생성

실행 방법:
  python run_daily.py                          # 어제 데이터 자동 처리
  python run_daily.py --date 2026-04-16        # 특정 날짜 처리
  python run_daily.py --since 2026-04-01 --until 2026-04-16  # 범위 처리

Windows 작업 스케줄러:
  schtasks /create /sc DAILY /tn "ReNK_Daily_Report" /tr "python C:\\path\\to\\run_daily.py" /st 09:00

Mac/Linux crontab:
  0 9 * * * cd /path/to/folder && python run_daily.py >> logs/daily.log 2>&1
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


# ============================================================
# 설정
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

REPORT_CSV = os.path.join(
    SCRIPT_DIR,
    '리엔케이 26년 커머스 데이터 리포트_260105 - ReNK_SUMMARY 3월.csv'
)
_base = os.path.splitext(REPORT_CSV)[0]
OUTPUT_CSV = _base + '_업데이트.csv'

LOG_DIR = os.path.join(SCRIPT_DIR, 'logs')
REPORT_DIR = os.path.join(SCRIPT_DIR, 'reports')
DATA_DIR = os.path.join(SCRIPT_DIR, 'data')


# ============================================================
# 로그
# ============================================================

def log(msg: str, level: str = 'INFO'):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] [{level}] {msg}"
    print(line)
    return line


def ensure_dirs():
    for d in [LOG_DIR, REPORT_DIR, DATA_DIR]:
        os.makedirs(d, exist_ok=True)


# ============================================================
# 매체별 데이터 수집
# ============================================================

def collect_meta(since, until):
    """Meta API 수집 (자사몰 + 스마트스토어)"""
    try:
        from meta_api_fetcher import (
            fetch_account_insights, fetch_campaign_insights, save_to_csv, CONFIG
        )
    except ImportError as e:
        log(f"Meta 모듈 임포트 실패: {e}", 'WARN')
        return {}, {}, {}, {}

    prev_date = (datetime.strptime(since, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

    log("  Meta API: 계정 데이터 수집 중...")
    ss_data = fetch_account_insights(CONFIG['ACCOUNT_SS'], prev_date, until, '스마트스토어')
    own_data = fetch_account_insights(CONFIG['ACCOUNT_OWN'], prev_date, until, '자사몰')

    log("  Meta API: 캠페인 데이터 수집 중...")
    own_campaigns = fetch_campaign_insights(CONFIG['ACCOUNT_OWN'], since, until, '자사몰 캠페인')
    ss_campaigns = fetch_campaign_insights(CONFIG['ACCOUNT_SS'], since, until, '스마트스토어 캠페인')

    # 백업 저장
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    if ss_data:
        save_to_csv(ss_data, os.path.join(DATA_DIR, f"meta_ss_{ts}.csv"))
    if own_data:
        save_to_csv(own_data, os.path.join(DATA_DIR, f"meta_own_{ts}.csv"))

    return own_data or {}, ss_data or {}, own_campaigns or {}, ss_campaigns or {}


def collect_cafe24(since, until):
    """카페24 자사몰 매출 수집"""
    try:
        from cafe24_api_fetcher import fetch_daily_data as cafe24_fetch
    except ImportError:
        log("  카페24 모듈 미설치 — 자사몰 커머스 수치 수동 입력 필요", 'WARN')
        return {}

    log("  카페24 API: 자사몰 매출 수집 중...")
    cafe24_data = {}
    current = datetime.strptime(since, '%Y-%m-%d')
    end = datetime.strptime(until, '%Y-%m-%d')
    prev = current - timedelta(days=1)

    for d in [prev] + [current + timedelta(days=i) for i in range((end - current).days + 1)]:
        d_str = d.strftime('%Y-%m-%d')
        try:
            result = cafe24_fetch(d_str)
            if result and result.get('order_count', 0) > 0:
                cafe24_data[d_str] = result
        except Exception as e:
            log(f"  카페24 {d_str} 실패: {e}", 'WARN')

    if cafe24_data:
        log(f"  카페24 {len(cafe24_data)}일 데이터 수집 완료")
    return cafe24_data


def collect_cafe24_top_products(date_str):
    """카페24 상품 판매 TOP 3 수집"""
    try:
        from cafe24_top_products import fetch_top_products
    except ImportError:
        log("  카페24 상품TOP 모듈 미설치", 'WARN')
        return []

    log(f"  카페24 상품 TOP 3 수집 중 ({date_str})...")
    try:
        top3 = fetch_top_products(date_str, top_n=3)
        if top3:
            for i, p in enumerate(top3):
                log(f"    #{i+1} {p['product_name'][:30]} — {p['amount']:,}원 ({p['quantity']}개)")
        return top3
    except Exception as e:
        log(f"  카페24 상품TOP 수집 실패: {e}", 'WARN')
        return []


def collect_naver(since, until):
    """네이버 검색광고 데이터 수집"""
    try:
        from naver_api_fetcher import fetch_naver_data
    except ImportError:
        log("  네이버 모듈 미설치 — 네이버 SA/BS/쇼검 수동 입력 필요", 'WARN')
        return {}

    log("  네이버 검색광고 API: 데이터 수집 중...")
    try:
        prev_date = (datetime.strptime(since, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        return fetch_naver_data(prev_date, until)
    except Exception as e:
        log(f"  네이버 수집 실패: {e}", 'WARN')
        return {}


def collect_google(since, until):
    """Google Ads 데이터 수집"""
    try:
        from google_ads_fetcher import fetch_google_data
    except ImportError:
        log("  Google Ads 모듈 미설치 — Google 수동 입력 필요", 'WARN')
        return {}

    log("  Google Ads API: 데이터 수집 중...")
    try:
        prev_date = (datetime.strptime(since, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        return fetch_google_data(prev_date, until)
    except Exception as e:
        log(f"  Google Ads 수집 실패: {e}", 'WARN')
        return {}


def post_to_slack(date_str, report_path):
    """Slack 채널에 docx 보고서 파일 업로드 + Google Sheets 링크 전달"""
    try:
        from slack_uploader import load_config, upload_file_to_channel
    except ImportError:
        log("  slack_uploader 모듈 없음 — Slack 발행 건너뜀", 'WARN')
        return False

    config = load_config()
    if not config:
        log("  Slack 설정 파일 없음 — Slack 발행 건너뜀", 'WARN')
        return False

    token = config.get('user_token') or config.get('bot_token')
    channel = config.get('channel_id', '')
    if not token or not channel:
        log("  Slack 토큰 또는 채널 미설정", 'WARN')
        return False

    log(f"  Slack 파일 업로드: {os.path.basename(report_path)}")
    success = upload_file_to_channel(report_path, channel, token)
    if success:
        log(f"  Slack 발행 완료: #{config.get('channel_name', channel)}")
    else:
        log("  Slack 발행 실패", 'ERROR')
    return success


def collect_smartstore(since, until):
    """네이버 스마트스토어 커머스 데이터 수집"""
    try:
        from smartstore_api_fetcher import fetch_smartstore_data
    except ImportError:
        log("  스마트스토어 모듈 미설치 — 스마트스토어 커머스 수동 입력 필요", 'WARN')
        return {}

    log("  스마트스토어 커머스 API: 매출 데이터 수집 중...")
    try:
        prev_date = (datetime.strptime(since, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        return fetch_smartstore_data(prev_date, until)
    except Exception as e:
        log(f"  스마트스토어 수집 실패: {e}", 'WARN')
        return {}


def collect_ga4(since, until):
    """GA4 웹 트래픽 데이터 수집"""
    try:
        from ga4_api_fetcher import fetch_ga4_data
    except ImportError:
        log("  GA4 모듈 미설치 — GA4 데이터 수동 확인 필요", 'WARN')
        return {}

    log("  GA4 Data API: 웹 트래픽 데이터 수집 중...")
    try:
        prev_date = (datetime.strptime(since, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
        return fetch_ga4_data(prev_date, until)
    except Exception as e:
        log(f"  GA4 수집 실패: {e}", 'WARN')
        return {}


# ============================================================
# Google Sheets 아카이빙
# ============================================================

def archive_to_sheets(date_str, own, ss, naver_data, google_data, cafe24,
                       top_products=None, smartstore=None):
    """Google Sheets에 일별 데이터 기입 (매체별 시트 분리)"""
    try:
        from google_sheets_writer import append_daily_data
    except ImportError:
        log("  Google Sheets 모듈 미설치 — 아카이빙 건너뜀", 'WARN')
        return False

    try:
        nv = naver_data.get(date_str, {})
        ggl = google_data.get(date_str, {})
        result = append_daily_data(date_str, own, ss, nv, ggl, cafe24, top_products, smartstore)
        if result:
            log(f"  Google Sheets 기입 완료: {date_str}")
        return result
    except Exception as e:
        log(f"  Google Sheets 기입 실패: {e}", 'WARN')
        return False


# ============================================================
# docx 보고서 생성
# ============================================================

def generate_docx_report(date_str, own, ss, own_campaigns, ss_campaigns,
                          prev_own, prev_ss, cafe24, prev_cafe24,
                          naver_data, google_data, top_products=None,
                          ga4_data=None, smartstore=None, prev_smartstore=None):
    """Node.js generate_daily_report.js 호출 → docx 생성"""
    prev_date = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    report_data = {
        'date': date_str,
        'own': own,
        'ss': ss,
        'own_campaigns': own_campaigns,
        'ss_campaigns': ss_campaigns,
        'prev_own': prev_own,
        'prev_ss': prev_ss,
        'cafe24': cafe24,
        'prev_cafe24': prev_cafe24,
        'naver': naver_data.get(date_str, {}),
        'prev_naver': naver_data.get(prev_date, {}),
        'google': google_data.get(date_str, {}),
        'prev_google': google_data.get(prev_date, {}),
        'top_products': top_products or [],
        'ga4': (ga4_data or {}).get(date_str, {}),
        'prev_ga4': (ga4_data or {}).get(prev_date, {}),
        'smartstore_commerce': smartstore or {},
        'prev_smartstore_commerce': prev_smartstore or {},
    }

    data_path = os.path.join(DATA_DIR, f"report_data_{date_str}.json")
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)

    dt = datetime.strptime(date_str, '%Y-%m-%d')
    weekdays = ['월', '화', '수', '목', '금', '토', '일']
    wd = weekdays[dt.weekday()]
    output_name = f"ReNK_Daily_Report_{date_str}({wd}).docx"
    output_path = os.path.join(REPORT_DIR, output_name)

    generator_path = os.path.join(SCRIPT_DIR, 'generate_daily_report.js')
    if not os.path.exists(generator_path):
        log(f"docx 생성기 없음: {generator_path}", 'ERROR')
        return None

    # 파일 잠금 방지: 기존 파일이 열려 있으면 대체 파일명 사용
    final_output = output_path
    if os.path.exists(output_path):
        try:
            with open(output_path, 'a'):
                pass  # 쓰기 가능 여부 확인
        except (PermissionError, OSError):
            ts = datetime.now().strftime('%H%M%S')
            alt_name = f"ReNK_Daily_Report_{date_str}({wd})_{ts}.docx"
            final_output = os.path.join(REPORT_DIR, alt_name)
            log(f"  기존 파일 잠김 → 대체 파일명: {alt_name}", 'WARN')

    try:
        result = subprocess.run(
            ['node', generator_path, data_path, final_output],
            capture_output=True, timeout=30,
            cwd=SCRIPT_DIR,
            encoding='utf-8', errors='replace',
        )
        if result.returncode == 0:
            log(f"  docx 보고서 생성 완료: {os.path.basename(final_output)}")
            return final_output
        else:
            log(f"  docx 생성 실패: {result.stderr}", 'ERROR')
            return None
    except FileNotFoundError:
        log("  Node.js 미설치 — docx 보고서 생성 불가", 'ERROR')
        return None
    except subprocess.TimeoutExpired:
        log("  docx 생성 타임아웃", 'ERROR')
        return None


# ============================================================
# 리포트 CSV 기입 (하위 호환)
# ============================================================

def update_csv_report(report_csv, output_csv, ss_data, own_data):
    """기존 CSV 리포트 자동 기입"""
    try:
        from meta_processor import update_report, validate_data
    except ImportError:
        log("  meta_processor 모듈 없음 — CSV 기입 건너뜀", 'WARN')
        return {}

    if ss_data:
        validate_data(ss_data, "스마트스토어")
    if own_data:
        validate_data(own_data, "자사몰")

    return update_report(report_csv, ss_data, own_data, output_csv)


# ============================================================
# 메인 파이프라인
# ============================================================

def run_pipeline(since: str, until: str, report_csv: str, output_csv: str = None):
    """전체 파이프라인 실행"""
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log(f"Re:NK Daily 자동화 v3 시작 ({since} ~ {until})")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # ── Step 1: 전체 매체 데이터 수집 ──
    log("Step 1: 전체 매체 데이터 수집")

    own_data, ss_data, own_campaigns, ss_campaigns = collect_meta(since, until)
    cafe24_data = collect_cafe24(since, until)
    smartstore_data = collect_smartstore(since, until)
    naver_data = collect_naver(since, until)
    google_data = collect_google(since, until)
    ga4_data = collect_ga4(since, until)

    has_data = bool(own_data or ss_data)
    if not has_data:
        log("Meta 데이터 없음. 해당 기간 광고 미집행 또는 API 오류.", 'WARN')

    # ── Step 2: CSV 리포트 기입 (하위 호환) ──
    if os.path.exists(report_csv):
        log("Step 2: CSV 리포트 기입")
        update_csv_report(report_csv, output_csv, ss_data, own_data)

    # ── Step 3: Google Sheets 아카이빙 + docx 보고서 생성 ──
    log("Step 3: Google Sheets 아카이빙 + docx 보고서 생성")

    current = datetime.strptime(since, '%Y-%m-%d')
    end = datetime.strptime(until, '%Y-%m-%d')
    prev_d_func = lambda d: (datetime.strptime(d, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

    while current <= end:
        d = current.strftime('%Y-%m-%d')
        prev_d = prev_d_func(d)

        own = own_data.get(d, {})
        ss = ss_data.get(d, {})
        prev_own = own_data.get(prev_d, {})
        prev_ss = ss_data.get(prev_d, {})
        c24 = cafe24_data.get(d, {})
        prev_c24 = cafe24_data.get(prev_d, {})
        own_camp = own_campaigns.get(d, [])
        ss_camp = ss_campaigns.get(d, [])

        ggl = google_data.get(d, {})
        nv = naver_data.get(d, {})

        # 스마트스토어 커머스
        sst = smartstore_data.get(d, {})

        # 카페24 상품 TOP 3
        top_products = collect_cafe24_top_products(d) if c24.get('order_count', 0) > 0 else []

        # 항상 기입 (데이터 없으면 0으로 채움)
        if True:
            # Google Sheets 아카이빙
            archive_to_sheets(d, own, ss, naver_data, google_data, c24, top_products, sst)

            # docx 보고서
            prev_sst = smartstore_data.get(prev_d, {})
            report_path = generate_docx_report(
                d, own, ss, own_camp, ss_camp,
                prev_own, prev_ss, c24, prev_c24,
                naver_data, google_data, top_products,
                ga4_data, sst, prev_sst,
            )

        current += timedelta(days=1)

    # ── Step 4: 결과 요약 ──
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log("결과 요약")

    current = datetime.strptime(since, '%Y-%m-%d')
    while current <= end:
        d = current.strftime('%Y-%m-%d')
        own = own_data.get(d, {})
        ss = ss_data.get(d, {})
        nv = naver_data.get(d, {})
        ggl = google_data.get(d, {})
        c24 = cafe24_data.get(d, {})
        sst = smartstore_data.get(d, {})
        ga4 = ga4_data.get(d, {})

        if True:  # 항상 요약 출력
            own_cost = own.get('cost', 0)
            own_rev = own.get('revenue', 0)
            own_roas = int(own_rev / own_cost * 100) if own_cost > 0 else 0
            ss_cost = ss.get('cost', 0)
            ss_cpas = ss.get('cpas_revenue', 0)
            ss_roas = int(ss_cpas / ss_cost * 100) if ss_cost > 0 else 0

            log(f"  {d}:")
            log(f"    META 자사몰     광고비 {int(own_cost):,}원 | 매출 {int(own_rev):,}원 | ROAS {own_roas}%")
            log(f"    META 스마트스토어 광고비 {int(ss_cost):,}원 | CPAS 전환값 {int(ss_cpas):,}원 | ROAS {ss_roas}%")

            if nv:
                nv_sa = nv.get('sa', {})
                log(f"    네이버 SA      광고비 {nv_sa.get('cost', 0):,}원 | 클릭 {nv_sa.get('clicks', 0)}")

            if ggl:
                ggl_t = ggl.get('total', {})
                log(f"    Google Ads     광고비 {ggl_t.get('cost', 0):,}원 | 클릭 {ggl_t.get('clicks', 0)}")

            if c24 and c24.get('order_count', 0) > 0:
                log(f"    카페24 자사몰   결제합계 {c24['paid_amount']:,}원 | 환불 {c24.get('refund_amount',0):,}원 | 순매출 {c24.get('net_sales',0):,}원 | 주문 {c24['order_count']}건")

            if sst and sst.get('order_count', 0) > 0:
                log(f"    스마트스토어    결제합계 {sst.get('paid_amount',0):,}원 | 환불 {sst.get('refund_amount',0):,}원 | 순매출 {sst.get('net_revenue',0):,}원 | 주문 {sst['order_count']}건")

            if ga4 and ga4.get('overview'):
                ov = ga4['overview']
                log(f"    GA4            세션 {ov.get('sessions', 0):,} | 사용자 {ov.get('users', 0):,} | 신규 {ov.get('new_users', 0):,} | 구매 {ov.get('purchases', 0)}건 | 이탈률 {ov.get('bounce_rate', 0)*100:.1f}%")

            total_cost = int(own_cost + ss_cost + nv.get('sa', {}).get('cost', 0) + ggl.get('total', {}).get('cost', 0))
            log(f"    ─ 전체 매체 합산 광고비: {total_cost:,}원")

        current += timedelta(days=1)

    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log("파이프라인 완료")
    log(f"  보고서 폴더: {REPORT_DIR}")
    log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Re:NK 일간 통합 자동화 v3')
    parser.add_argument('--date', help='처리 날짜 (YYYY-MM-DD)')
    parser.add_argument('--since', help='시작일 (YYYY-MM-DD)')
    parser.add_argument('--until', help='종료일 (YYYY-MM-DD)')
    parser.add_argument('--slack', action='store_true', help='Slack 보고서 발행 (별도 실행)')
    parser.add_argument('--report-csv', default=REPORT_CSV, help='리포트 CSV 경로')
    parser.add_argument('--output', default=OUTPUT_CSV, help='출력 CSV 경로')
    args = parser.parse_args()

    if args.date:
        since = until = args.date
    elif args.since and args.until:
        since = args.since
        until = args.until
    else:
        yesterday = datetime.now() - timedelta(days=1)
        since = until = yesterday.strftime('%Y-%m-%d')

    ensure_dirs()

    # --slack 모드: 보고서 파일 찾아서 Slack 발행만 실행
    if args.slack:
        from slack_uploader import find_report
        report_path = find_report(since)
        if not report_path:
            log(f"{since} 보고서 파일 없음 (reports/ 폴더 확인)", 'ERROR')
            sys.exit(1)
        log(f"Slack 발행: {os.path.basename(report_path)}")
        success = post_to_slack(since, report_path)
        sys.exit(0 if success else 1)

    try:
        run_pipeline(since, until, args.report_csv, args.output)
    except KeyboardInterrupt:
        log("사용자 중단", 'WARN')
        sys.exit(0)
    except Exception as e:
        log(f"오류: {e}", 'ERROR')
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
