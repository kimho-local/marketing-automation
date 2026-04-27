#!/usr/bin/env python3
"""
카페24 커머스 시트 열 순서 마이그레이션
=======================================
기존(11열): 날짜, 결제합계, 환불합계, 순매출, 주문건수, 구매자수, 방문자수, 객단가, 상품구매금액, 월, 주차
신규(15열): 날짜, 결제합계, 환불합계, 순매출, 주문건수, 구매자수, 첫구매, 재구매, 첫구매비율(%), 재구매비율(%), 방문자수, 객단가, 상품구매금액, 월, 주차

A~F 유지, G~K(구) → G~O(신)으로 재배치
"""

import sys
import os

# google_sheets_writer에서 인증/API 함수 재사용
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from google_sheets_writer import (
    load_config, get_access_token, sheets_get, sheets_update
)

SHEET_NAME = '카페24 커머스'


def migrate():
    config = load_config()
    if not config:
        return False

    sid = config.get('spreadsheet_id', '')
    token = get_access_token()
    if not sid or not token:
        print("[ERROR] 인증 실패")
        return False

    # 1) 전체 데이터 읽기
    result = sheets_get(sid, f"'{SHEET_NAME}'!A:O", token)
    rows = result.get('values', [])

    if len(rows) < 2:
        print("데이터 없음")
        return False

    header = rows[0]
    print(f"현재 헤더: {header}")
    print(f"데이터 행: {len(rows) - 1}건")

    # 2) 각 데이터 행 재배치
    new_rows = []
    for i, row in enumerate(rows[1:], start=2):
        # 열 수 부족하면 패딩
        while len(row) < 15:
            row.append('')

        # A~F (인덱스 0~5) 유지
        a_f = row[0:6]

        # 기존 데이터 판별: G열에 숫자(방문자수)가 있고, K열에 "2026-" 같은 월 텍스트가 있으면 구(舊) 형식
        old_g = row[6]   # 구: 방문자수
        old_h = row[7]   # 구: 객단가
        old_i = row[8]   # 구: 상품구매금액
        old_j = row[9]   # 구: 월 (또는 첫구매)
        old_k = row[10]  # 구: 주차 (또는 재구매)

        # 구 형식 판별: J열에 "2026-" 또는 "202" 이 포함되면 구 형식 (월 텍스트)
        is_old_format = isinstance(old_j, str) and ('2026-' in old_j or '2025-' in old_j or '202' in old_j)

        if is_old_format:
            # 구(11열) → 신(15열) 변환
            visitor = old_g       # 방문자수
            avg_price = old_h     # 객단가
            product_amt = old_i   # 상품구매금액

            new_row = a_f + [
                0,                                                              # G: 첫구매
                0,                                                              # H: 재구매
                f'=ROUND(IF(G{i}+H{i}>0,G{i}/(G{i}+H{i})*100,0),1)',        # I: 첫구매비율(%)
                f'=ROUND(IF(G{i}+H{i}>0,H{i}/(G{i}+H{i})*100,0),1)',        # J: 재구매비율(%)
                visitor,                                                        # K: 방문자수
                f'=ROUND(IF(E{i}>0,D{i}/E{i},0),0)',                          # L: 객단가 (수식)
                product_amt,                                                    # M: 상품구매금액
                f'=TEXT(A{i},"YYYY-MM")',                                      # N: 월
                f'=MONTH(A{i})&"월-"&INT((DAY(A{i})-1)/7)+1&"주차"',         # O: 주차
            ]
            new_rows.append(new_row)
            print(f"  행 {i}: 구→신 변환 (방문자수={visitor})")
        else:
            # 이미 신 형식이거나 중간 형식 → 그대로
            new_rows.append(row[:15])
            print(f"  행 {i}: 유지")

    # 3) 전체 덮어쓰기 (헤더 제외, 2행부터)
    if new_rows:
        print(f"\n총 {len(new_rows)}행 업데이트 중...")
        # 50행 단위로 나눠서 쓰기
        batch_size = 50
        for start in range(0, len(new_rows), batch_size):
            batch = new_rows[start:start + batch_size]
            row_start = start + 2  # 2행부터
            range_str = f"'{SHEET_NAME}'!A{row_start}:O{row_start + len(batch) - 1}"
            result = sheets_update(sid, range_str, batch, token)
            if result:
                print(f"  [OK] 행 {row_start}~{row_start + len(batch) - 1} 업데이트 완료")
            else:
                print(f"  [ERROR] 행 {row_start}~{row_start + len(batch) - 1} 실패")
                return False

    print("\n마이그레이션 완료!")
    return True


if __name__ == '__main__':
    migrate()
