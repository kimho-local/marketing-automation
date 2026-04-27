# CHANGELOG — 카페24 첫구매/재구매 자동화 (2026-04-27)

## 요약
카페24 자사몰 주문 데이터에서 첫구매/재구매 고객을 자동 판별하는 기능 추가.
docx 보고서, Google Sheets, 종합 코멘트에 첫구매/재구매 수치 반영 완료.

---

## 1. 카페24 API: 첫구매/재구매 판별 로직 추가

### 변경 파일
- `cafe24_api_fetcher.py` — `_count_first_repeat(date_str)` 함수 신규

### 로직
1. 당일 주문 전체 수집 (`/admin/orders`)
2. 고유 구매자 분류 (member_id 기준, 비회원은 첫구매로 간주)
3. 회원별 이전 주문 이력 확인 (`/admin/orders/count`)
   - 이전 주문 있음 → 재구매
   - 이전 주문 없음 → 첫구매
4. `fetch_daily_data()` 반환값에 first_buyers, repeat_buyers, first_ratio, repeat_ratio 추가

### API 제약 대응
- 카페24 `/admin/orders/count`는 start_date ~ end_date 범위 최대 6개월 제한
- `start_date`를 `2026-02-19`(운영 시작일)로 고정하여 제한 내 처리
- 회원별 개별 API 호출 → 0.3초 딜레이로 Rate Limit 대응

---

## 2. Google Sheets: 열 순서 변경 + 첫구매/재구매 열 삽입

### 변경 파일
- `google_sheets_writer.py` — 헤더, `make_cafe24_row()`, 서식 정의

### 변경 전 (11열)
날짜 | 결제합계 | 환불합계 | 순매출 | 주문건수 | 구매자수 | **방문자수** | **객단가** | **상품구매금액** | 월 | 주차

### 변경 후 (15열)
날짜 | 결제합계 | 환불합계 | 순매출 | 주문건수 | 구매자수 | **첫구매** | **재구매** | **첫구매비율(%)** | **재구매비율(%)** | 방문자수 | 객단가 | 상품구매금액 | 월 | 주차

### 수식 열
- I열: `=ROUND(IF(G+H>0, G/(G+H)*100, 0), 1)` — 첫구매비율(%)
- J열: `=ROUND(IF(G+H>0, H/(G+H)*100, 0), 1)` — 재구매비율(%)

---

## 3. docx 보고서: 첫구매/재구매 테이블 + 종합 코멘트

### 변경 파일
- `generate_daily_report.js` — `cafe24BuyerTypeTable()` 함수 신규, `generateSummaryComment()` 수정

### 추가 내용
- 카페24 섹션에 6열 가로형 테이블: 날짜 / 첫구매 / 재구매 / 총 구매자 / 첫구매 비율 / 재구매 비율
- 전일 대비 증감률 행 포함 (비율은 %p 단위)
- 종합 코멘트에 "자사몰 첫구매 N명(N%) / 재구매 N명(N%)" 라인 자동 삽입

---

## 4. 소급 백필 + 마이그레이션 스크립트

### 신규 파일
- `backfill/backfill_first_repeat.py` — 2/19~어제까지 첫구매/재구매 소급 조회 → 시트 G·H열 기입
- `backfill/fix_cafe24_columns.py` — 기존 데이터 행 열 순서 재배치 (구 11열 → 신 15열)

### 사용법
```bash
py backfill/fix_cafe24_columns.py                    # 열 순서 마이그레이션
py backfill/backfill_first_repeat.py                  # 전체 소급 백필
py backfill/backfill_first_repeat.py --since 2026-04-01  # 부분 백필
```

---

## 파일 변경 요약

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `cafe24_api_fetcher.py` | 수정 | `_count_first_repeat()` 추가, start_date 제약 대응 |
| `google_sheets_writer.py` | 수정 | 카페24 커머스 헤더/행/서식 열 순서 변경 |
| `generate_daily_report.js` | 수정 | 첫구매/재구매 테이블 + 종합 코멘트 반영 |
| `backfill/backfill_first_repeat.py` | 신규 | 소급 백필 스크립트 |
| `backfill/fix_cafe24_columns.py` | 신규 | 시트 열 마이그레이션 스크립트 |
