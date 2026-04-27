#!/usr/bin/env python3
"""
Re:NK META 광고 데이터 → 커머스 리포트 자동 기입 스크립트
==========================================================
발렌라이프 비즈니스 포트폴리오 > 리엔케이 클라이언트 계정
- 메타(스마트스토어) 계정
- 메타(자사몰) 계정

사용법:
  python meta_processor.py --meta-csv meta_export.csv --report-csv report.csv --date 2026-03-27
  python meta_processor.py --ss-csv smartstore.csv --own-csv ownmall.csv --report-csv report.csv
"""

import csv
import sys
import os
import re
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================
# 1. META CSV 컬럼 매핑 (Meta Ads Manager 내보내기 기준)
# ============================================================

# Meta Ads Manager에서 내보내는 CSV의 대표적인 컬럼명 변환
META_COLUMN_MAP = {
    # 한국어 내보내기
    '비용': 'cost',
    '금액 사용': 'cost',
    '지출 금액': 'cost',
    '결과당 비용': None,  # skip
    '노출': 'impressions',
    '노출수': 'impressions',
    '도달': None,
    '클릭(전체)': 'clicks',
    '링크 클릭': 'clicks',
    '클릭수': 'clicks',
    '구매': 'purchases',
    '구매 수': 'purchases',
    '전환값': 'revenue',
    '구매 전환값': 'revenue',
    '구매 전환 값': 'revenue',
    '웹사이트 구매 전환값': 'revenue',
    '웹사이트 구매': 'purchases',
    '동영상 조회': 'views',
    'ThruPlay': 'views',
    '날짜': 'date',
    '보고 시작': 'date',
    '일': 'date',
    '캠페인 이름': 'campaign',
    '캠페인명': 'campaign',
    '광고 세트 이름': 'adset',
    '광고 세트명': 'adset',

    # 영어 내보내기
    'Amount spent': 'cost',
    'Amount Spent': 'cost',
    'Cost': 'cost',
    'Impressions': 'impressions',
    'Clicks (all)': 'clicks',
    'Link clicks': 'clicks',
    'Link Clicks': 'clicks',
    'Purchases': 'purchases',
    'Purchase': 'purchases',
    'Purchase ROAS': None,
    'Conversion value': 'revenue',
    'Purchase conversion value': 'revenue',
    'Website purchases': 'purchases',
    'Website purchase conversion value': 'revenue',
    'Video plays': 'views',
    'Date': 'date',
    'Day': 'date',
    'Reporting starts': 'date',
    'Campaign name': 'campaign',
    'Ad set name': 'adset',
    'Ad Set Name': 'adset',
}

# 요일 매핑
WEEKDAY_KR = ['월', '화', '수', '목', '금', '토', '일']


def parse_number(val):
    """숫자 파싱: 쉼표, 통화기호, 공백 제거"""
    if val is None or val == '' or val == '-' or val == '#N/A':
        return 0
    val = str(val).strip()
    val = re.sub(r'[₩$,\s\u00a0]', '', val)
    val = val.replace('원', '')
    try:
        return float(val)
    except ValueError:
        return 0


def parse_date(val):
    """날짜 파싱: 다양한 포맷 지원"""
    val = str(val).strip()
    formats = [
        '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d',
        '%m/%d/%Y', '%m/%d/%y',
        '%d/%m/%Y', '%Y-%m-%dT%H:%M:%S',
        '%b %d, %Y', '%B %d, %Y',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def calc_derived(row):
    """파생 지표 계산 (0 나누기 방지)"""
    cost = row.get('cost', 0)
    revenue = row.get('revenue', 0)
    impressions = row.get('impressions', 0)
    clicks = row.get('clicks', 0)
    views = row.get('views', 0)
    purchases = row.get('purchases', 0)

    result = dict(row)
    result['ctr'] = (clicks / impressions * 100) if impressions > 0 else 0
    result['vtr'] = (views / impressions * 100) if impressions > 0 and views > 0 else 0
    result['cpc'] = int(cost / clicks) if clicks > 0 else 0
    result['cpv'] = int(cost / views) if views > 0 else 0
    result['cpm'] = int(cost / impressions * 1000) if impressions > 0 else 0
    result['cvr'] = (purchases / clicks * 100) if clicks > 0 else 0
    result['cpa'] = int(cost / purchases) if purchases > 0 else 0
    result['aov'] = int(revenue / purchases) if purchases > 0 else 0
    result['roas'] = int(revenue / cost * 100) if cost > 0 else 0
    return result


# ============================================================
# 2. META CSV 파싱
# ============================================================

def detect_encoding(filepath):
    """파일 인코딩 감지"""
    encodings = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'latin-1']
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                f.read(1000)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return 'utf-8'


def parse_meta_csv(filepath, account_label=None):
    """
    Meta Ads Manager CSV 파싱

    Args:
        filepath: CSV 파일 경로
        account_label: '스마트스토어' 또는 '자사몰' (선택)

    Returns:
        dict: {날짜: {cost, revenue, impressions, clicks, views, purchases}}
    """
    enc = detect_encoding(filepath)
    daily_data = defaultdict(lambda: {
        'cost': 0, 'revenue': 0, 'impressions': 0,
        'clicks': 0, 'views': 0, 'purchases': 0
    })

    with open(filepath, 'r', encoding=enc) as f:
        # BOM 제거 및 빈 줄 스킵
        content = f.read().strip()
        lines = [l for l in content.split('\n') if l.strip()]

    if not lines:
        print(f"[경고] 빈 파일: {filepath}")
        return daily_data

    # 헤더 감지 (첫 번째 줄 또는 데이터가 시작되는 줄)
    reader = csv.DictReader(lines)

    # 컬럼 매핑
    col_map = {}
    for orig_col in reader.fieldnames or []:
        clean = orig_col.strip().replace('\ufeff', '')
        if clean in META_COLUMN_MAP and META_COLUMN_MAP[clean] is not None:
            col_map[orig_col] = META_COLUMN_MAP[clean]

    if 'date' not in col_map.values():
        print(f"[경고] 날짜 컬럼을 찾을 수 없습니다: {filepath}")
        print(f"  발견된 컬럼: {reader.fieldnames}")
        return daily_data

    # 역 매핑: 내부명 → 원본 컬럼명
    reverse_map = {}
    for orig, internal in col_map.items():
        if internal not in reverse_map:
            reverse_map[internal] = orig

    for row in reader:
        # 날짜 추출
        date_col = reverse_map.get('date')
        if not date_col or not row.get(date_col):
            continue
        dt = parse_date(row[date_col])
        if not dt:
            continue
        date_key = dt.strftime('%Y-%m-%d')

        # 지표 합산
        for internal_name in ['cost', 'revenue', 'impressions', 'clicks', 'views', 'purchases']:
            orig_col = reverse_map.get(internal_name)
            if orig_col and row.get(orig_col):
                daily_data[date_key][internal_name] += parse_number(row[orig_col])

    print(f"[완료] {filepath}: {len(daily_data)}일 데이터 파싱 (계정: {account_label or '전체'})")
    return dict(daily_data)


# ============================================================
# 3. 리포트 CSV 읽기/쓰기
# ============================================================

def read_report_csv(filepath):
    """기존 리포트 CSV 전체를 읽어서 구조 보존"""
    enc = detect_encoding(filepath)
    with open(filepath, 'r', encoding=enc) as f:
        reader = csv.reader(f)
        rows = list(reader)
    return rows


def detect_col_offset(rows):
    """데이터가 시작되는 컬럼 오프셋 감지 (A열이 빈 경우 B열=1)"""
    for row in rows:
        for j, cell in enumerate(row):
            if '기간' in str(cell) or '날짜' in str(cell) or '매체' in str(cell):
                return j
    return 0


def find_daily_section(rows):
    """'04. 일별 데이터' 섹션의 시작 행과 데이터 행 범위, 컬럼 오프셋을 찾음"""
    header_row = None
    data_start = None
    col_offset = 0

    for i, row in enumerate(rows):
        # 섹션 헤더 찾기
        for cell in row:
            if '04. 일별 데이터' in str(cell) or '일별 데이터' in str(cell):
                header_row = i
                break

        # 컬럼 헤더 찾기 (기간, 요일, 광고비...)
        if header_row is not None and data_start is None:
            for j, cell in enumerate(row):
                if '기간' in str(cell) and any('광고비' in str(c) for c in row):
                    data_start = i + 1
                    col_offset = j  # 기간 컬럼의 위치가 오프셋
                    break

    return header_row, data_start, col_offset


def find_media_section(rows):
    """'매체별 데이터' 섹션에서 메타 행의 위치를 찾음"""
    meta_rows = {}
    in_media_section = False

    for i, row in enumerate(rows):
        for cell in row:
            if '매체별 데이터' in str(cell):
                in_media_section = True
                break

        if in_media_section:
            first_cell = str(row[0]).strip() if row else ''
            if '메타' in first_cell and '스마트스토어' in first_cell:
                meta_rows['smartstore'] = i
            elif '메타' in first_cell and '자사몰' in first_cell:
                meta_rows['ownmall'] = i
            # 다음 섹션이 시작되면 중단
            if first_cell and ('03.' in first_cell or '일별' in first_cell):
                break

    return meta_rows


def update_daily_row(rows, row_idx, data, col_offset=0):
    """일별 데이터 행을 업데이트 (col_offset: 데이터 시작 컬럼)"""
    needed = col_offset + 17
    while len(rows[row_idx]) < needed:
        rows[row_idx].append('')

    o = col_offset  # 오프셋 약칭
    # 컬럼 순서: [o+0]기간, [o+1]요일, [o+2]광고비, [o+3]매체매출, [o+4]노출, [o+5]클릭, [o+6]조회, [o+7]구매수,
    #            [o+8]CTR, [o+9]VTR, [o+10]CPC, [o+11]CPV, [o+12]CPM, [o+13]CVR, [o+14]CPA, [o+15]AOV, [o+16]ROAS
    d = calc_derived(data)
    date_str = data.get('date_str', '')

    if date_str:
        dt = parse_date(date_str)
        if dt:
            rows[row_idx][o+1] = WEEKDAY_KR[dt.weekday()]  # 요일

    rows[row_idx][o+2] = f"{int(d['cost']):,}" if d['cost'] > 0 else ''
    rows[row_idx][o+3] = f"{int(d['revenue']):,}" if d['revenue'] > 0 else ''
    rows[row_idx][o+4] = f"{int(d['impressions']):,}" if d['impressions'] > 0 else ''
    rows[row_idx][o+5] = f"{int(d['clicks']):,}" if d['clicks'] > 0 else ''
    rows[row_idx][o+6] = f"{int(d['views']):,}" if d['views'] > 0 else '0' if d['cost'] > 0 else ''
    rows[row_idx][o+7] = f"{int(d['purchases']):,}" if d['purchases'] > 0 else ''

    # 파생 지표
    rows[row_idx][o+8] = f"{d['ctr']:.2f}%" if d['ctr'] > 0 else '-%'
    rows[row_idx][o+9] = f"{d['vtr']:.2f}%" if d['vtr'] > 0 else '-%'
    rows[row_idx][o+10] = f"{d['cpc']:,}" if d['cpc'] > 0 else '-'
    rows[row_idx][o+11] = f"{d['cpv']:,}" if d['cpv'] > 0 else '-'
    rows[row_idx][o+12] = f"{d['cpm']:,}" if d['cpm'] > 0 else '-'
    rows[row_idx][o+13] = f"{d['cvr']:.2f}%" if d['cvr'] > 0 else '-%'
    rows[row_idx][o+14] = f"  {d['cpa']:,} " if d['cpa'] > 0 else '-'
    rows[row_idx][o+15] = f"{d['aov']:,}" if d['aov'] > 0 else '-'
    rows[row_idx][o+16] = f"{d['roas']}%" if d['roas'] > 0 else '-%'

    return rows


def update_report(report_path, meta_data_ss, meta_data_own, output_path=None):
    """
    기존 리포트 CSV에 META 데이터를 기입

    Args:
        report_path: 기존 리포트 CSV 경로
        meta_data_ss: 스마트스토어 일별 데이터 dict
        meta_data_own: 자사몰 일별 데이터 dict
        output_path: 출력 경로 (None이면 원본 덮어쓰기)
    """
    rows = read_report_csv(report_path)
    header_row, data_start, col_offset = find_daily_section(rows)

    if data_start is None:
        print("[오류] '04. 일별 데이터' 섹션을 찾을 수 없습니다.")
        return None

    print(f"  - 일별 데이터 섹션: 행 {data_start}, 컬럼 오프셋: {col_offset}")

    # 전체 META 합산 (스마트스토어 + 자사몰)
    all_dates = set(list(meta_data_ss.keys()) + list(meta_data_own.keys()))
    meta_total = {}
    for date_key in all_dates:
        ss = meta_data_ss.get(date_key, {})
        own = meta_data_own.get(date_key, {})
        meta_total[date_key] = {
            'cost': ss.get('cost', 0) + own.get('cost', 0),
            'revenue': ss.get('revenue', 0) + own.get('revenue', 0),
            'impressions': ss.get('impressions', 0) + own.get('impressions', 0),
            'clicks': ss.get('clicks', 0) + own.get('clicks', 0),
            'views': ss.get('views', 0) + own.get('views', 0),
            'purchases': ss.get('purchases', 0) + own.get('purchases', 0),
            'date_str': date_key,
        }

    # 일별 데이터 섹션에서 날짜 매칭하여 업데이트
    updated_dates = []
    for i in range(data_start, len(rows)):
        if not rows[i] or len(rows[i]) <= col_offset:
            continue
        date_cell = str(rows[i][col_offset]).strip()

        # 월간 TOTAL 행이면 중단하지 않고 계속 (여러 월 존재 가능)
        if 'TOTAL' in date_cell:
            continue

        # 빈 셀 스킵
        if not date_cell:
            continue

        # 날짜 파싱
        dt = parse_date(date_cell)
        if not dt:
            continue
        date_key = dt.strftime('%Y-%m-%d')

        if date_key in meta_total:
            data = meta_total[date_key]
            data['date_str'] = date_key
            update_daily_row(rows, i, data, col_offset)
            updated_dates.append(date_key)

    # 저장
    out = output_path or report_path
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    print(f"\n{'='*60}")
    print(f"[결과] 리포트 업데이트 완료")
    print(f"  - 업데이트된 날짜: {len(updated_dates)}일")
    for d in sorted(updated_dates):
        m = meta_total[d]
        derived = calc_derived(m)
        print(f"    {d}: 광고비 {int(m['cost']):,}원 | 매출 {int(m['revenue']):,}원 | ROAS {derived['roas']}%")
    print(f"  - 저장 위치: {out}")
    print(f"{'='*60}")

    return updated_dates


# ============================================================
# 4. 검증 로직
# ============================================================

def validate_data(meta_data, label=""):
    """데이터 품질 검증"""
    issues = []
    for date_key, d in sorted(meta_data.items()):
        # 빈 값 체크
        if d.get('cost', 0) == 0 and d.get('impressions', 0) == 0:
            issues.append(f"  ⚠️ {date_key}: 광고비/노출 모두 0 → 데이터 누락 가능성")

        # 구매=0 인데 매출>0
        if d.get('purchases', 0) == 0 and d.get('revenue', 0) > 0:
            issues.append(f"  ⚠️ {date_key}: 구매=0, 매출={int(d['revenue']):,}원 → 전환 추적 확인 필요")

        # ROAS 이상치
        if d.get('cost', 0) > 0:
            roas = d.get('revenue', 0) / d['cost'] * 100
            if roas > 1000:
                issues.append(f"  ⚠️ {date_key}: ROAS {int(roas)}% → 이상 수치 확인 필요")

    if issues:
        print(f"\n[검증 결과 - {label}]")
        for issue in issues:
            print(issue)
    else:
        print(f"\n[검증 결과 - {label}] 이상 없음 ✓")

    return issues


# ============================================================
# 5. 메인 실행
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Re:NK META 광고 데이터 리포트 자동 기입')

    # 통합 CSV (하나의 파일에 두 계정 데이터)
    parser.add_argument('--meta-csv', help='META 통합 CSV 파일')

    # 계정별 개별 CSV
    parser.add_argument('--ss-csv', help='스마트스토어 계정 CSV')
    parser.add_argument('--own-csv', help='자사몰 계정 CSV')

    # 리포트 파일
    parser.add_argument('--report-csv', required=True, help='기존 리포트 CSV')
    parser.add_argument('--output', help='출력 파일 (미지정시 원본 덮어쓰기)')

    # 옵션
    parser.add_argument('--date', help='특정 날짜만 처리 (YYYY-MM-DD)')
    parser.add_argument('--validate-only', action='store_true', help='검증만 수행')

    args = parser.parse_args()

    meta_ss = {}
    meta_own = {}

    if args.meta_csv:
        print(f"\n[1] META 통합 CSV 파싱: {args.meta_csv}")
        meta_all = parse_meta_csv(args.meta_csv)
        # 통합 파일의 경우 두 계정 합산으로 처리
        meta_ss = meta_all
        meta_own = {}
    else:
        if args.ss_csv:
            print(f"\n[1] 스마트스토어 CSV 파싱: {args.ss_csv}")
            meta_ss = parse_meta_csv(args.ss_csv, '스마트스토어')
        if args.own_csv:
            print(f"\n[2] 자사몰 CSV 파싱: {args.own_csv}")
            meta_own = parse_meta_csv(args.own_csv, '자사몰')

    if not meta_ss and not meta_own:
        print("[오류] META 데이터가 없습니다. --meta-csv 또는 --ss-csv/--own-csv를 지정하세요.")
        sys.exit(1)

    # 특정 날짜 필터
    if args.date:
        meta_ss = {k: v for k, v in meta_ss.items() if k == args.date}
        meta_own = {k: v for k, v in meta_own.items() if k == args.date}

    # 검증
    if meta_ss:
        validate_data(meta_ss, "스마트스토어")
    if meta_own:
        validate_data(meta_own, "자사몰")

    if args.validate_only:
        print("\n[검증 모드] 리포트 업데이트를 건너뜁니다.")
        return

    # 리포트 업데이트
    print(f"\n[3] 리포트 업데이트: {args.report_csv}")
    update_report(args.report_csv, meta_ss, meta_own, args.output)


if __name__ == '__main__':
    main()
