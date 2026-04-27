# CHANGELOG — 카페24 + Google Sheets 자동화 (2026-04-22)

## 요약
카페24 자사몰 매출 데이터 수집 자동화 구현 및 Google Sheets 백필 완료.
META 자사몰 / META 스마트스토어(협력광고) / 카페24 커머스 3개 시트 데이터 기입 완료.

---

## 카페24 API 전환: 주문 API → Dashboard API

### 문제
- 주문 건별 상세조회 기반 집계 시 대시보드와 수치 불일치
  - 결제합계: API 4,492,813원 vs 대시보드 5,040,000원 (11% 차이)
  - 환불합계: API 0원 vs 대시보드 467,000원
  - 구매자수: API 83명 vs 대시보드 95명

### 해결
- `/admin/dashboard` API 발견 → 대시보드와 100% 동일한 수치 반환
- 결제합계(`paid_price`), 환불합계(`refund_price`), 상품구매금액(`order_price`) 완벽 일치
- 구매자수: `billing_name` 기반 집계로 94명 달성 (대시보드 95명, 1명 차이)

### Dashboard API 제약
- 최근 2일만 반환 (과거 날짜 미지원)
- 일별 자동 수집(전일 데이터)에는 적합
- 과거 백필은 CSV 다운로드 기반으로 대체

---

## 변경 파일

### `cafe24_api_fetcher.py` — 전면 재작성
- 주문 건별 상세조회 → `/admin/dashboard` API 1회 호출로 전환
- `fetch_dashboard(start_date, end_date)`: Dashboard API 호출
- `_parse_dashboard_day(day)`: 응답 파싱 → 통합 데이터 dict
- `_count_unique_customers(date_str)`: billing_name 기반 구매자수 집계
- `fetch_daily_data(date_str)`: Dashboard API + 구매자수 보완
- `fetch_range(since, until)`: 범위 수집 (Dashboard 우선, 미지원 시 개별 호출)
- `test_connection()`: Dashboard API 테스트 + 날짜 범위 지원 여부 확인 포함

### `google_sheets_writer.py` — 카페24 커머스 시트 구조 변경
- 헤더: `날짜, 결제합계, 환불합계, 순매출, 주문건수, 구매자수, 방문자수, 객단가, 상품구매금액, 월, 주차` (11열, A:K)
- 순매출(D열): `=B-C` 수식 (결제합계 - 환불합계)
- 객단가(H열): `=ROUND(IF(E>0,D/E,0),0)` 수식 (순매출/주문건수)
- 방문자수(G열) 신규 추가

### `backfill_cafe24_csv.py` — 신규
- 카페24 대시보드 매출 CSV + 방문자/구매자 CSV 병합 파싱
- 인코딩 자동감지 (UTF-8/CP949)
- 헤더 자동매핑 (일자, 결제합계, 환불합계, 순매출, 주문수, 상품구매금액)
- Google Sheets 일괄 기입 (배치 방식)
- `--dry-run` 미리보기 지원

### `backfill_sheets.py` — 기존 META 백필 (변경 없음)
- META 자사몰 (2026-02-19 ~ 2026-04-20) 백필 완료
- META 스마트스토어 (2026-01-02 ~ 2026-04-20) 백필 완료

### `run_daily.py` — 요약 출력 수정
- 카페24 요약: `결제합계 | 환불 | 순매출 | 주문건수` 형태로 변경

---

## 탐색/진단 스크립트 (임시)
- `probe_salesreport.py` — 카페24 매출통계 API 엔드포인트 1차 탐색
- `probe_salesreport2.py` — salesvolume 파라미터 테스트
- `probe_salesreport3.py` — 주문 금액 필드별 합산 비교 진단
- `probe_customers.py` — 구매자수 필드별 정확도 비교

---

## Google Sheets 백필 현황

| 시트 | 기간 | 상태 |
|------|------|------|
| META 자사몰 | 2026-02-19 ~ 2026-04-20 | ✅ 완료 |
| META 스마트스토어 | 2026-01-02 ~ 2026-04-20 | ✅ 완료 |
| 카페24 커머스 | 2026-02-19 ~ 2026-04-20 | ✅ 완료 |
| 네이버 SA | 2026-01-23 ~ 2026-04-21 | ✅ 완료 |

---

## 남은 작업
- ~~네이버 SA 백필~~ ✅ 완료 (CHANGELOG_NAVER_SA_20260422.md 참조)
- ~~탐색 스크립트(probe_*.py) 정리/삭제~~ ✅ 완료
- Google Ads 연동
- Windows 작업 스케줄러 등록 (run_daily.py 자동 실행)
