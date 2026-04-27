# CHANGELOG — 네이버 검색광고(SA) 자동화 (2026-04-22)

## 요약
네이버 검색광고 API 연동 및 Google Sheets 백필 완료.
일별 캠페인 타입별 합산 구조로 89일(1/23~4/21) 데이터 기입.

---

## 네이버 검색광고 API 연동

### 인증 방식
- HMAC-SHA256 서명 (base64 인코딩, hex 아님)
- 헤더: `X-Timestamp`, `X-API-KEY`, `X-Customer`, `X-Signature`
- 고객번호(customer_id): 3445110

### 주요 발견사항

| 항목 | 내용 |
|------|------|
| `campaignTp` 값 | 문자열 (`WEB_SITE`, `SHOPPING`, `BRAND_SEARCH`, `POWER_CONTENTS`) |
| 구매완료 전환 필드 | `purchaseCcnt` (전환수), `purchaseConvAmt` (전환매출) |
| 총전환 필드 | `ccnt`, `convAmt` — 모든 전환 유형 포함, 구매완료와 다름 |
| 브랜드검색 광고비 | 0원 (월 고정비 모델, API 미포함) |
| `/stats` 필수 파라미터 | `ids`, `fields`(JSON 배열 문자열), `timeRange`(JSON 문자열) |
| `/stats` 주의사항 | `datePreset` 파라미터 포함 시 400 에러 |

### stats 조회 필드 (검증 완료)
`impCnt`, `clkCnt`, `salesAmt`, `cpc`, `ctr`, `ccnt`, `crto`, `convAmt`, `ror`, `purchaseCcnt`, `purchaseConvAmt`

---

## 변경/신규 파일

### `naver_api_fetcher.py` — 신규
- 네이버 검색광고 REST API 호출 (GET/POST)
- HMAC-SHA256 base64 서명 생성
- 캠페인 유형 분류 (`WEB_SITE`→파워링크, `SHOPPING`→쇼핑검색, `BRAND_SEARCH`→브랜드검색)
- `fetch_naver_data(since, until)`: 일별 통합 수집 (캠페인 타입별 합산)
- `fetch_naver_ad_rows(date_str)`: 소재 단위 수집 (현재 미사용, 확장용 보존)
- 인증파일: `renk_naver_credentials.json`

### `backfill_naver_sa.py` — 신규
- 네이버 SA → Google Sheets 과거 데이터 일괄 기입
- 1일씩 개별 수집 → 배치 append
- `--since`, `--until`, `--dry-run` CLI 옵션

### `google_sheets_writer.py` — 수정
- 네이버 SA 시트 헤더 추가 (16열, A:P)
- `make_naver_row()` 함수: 일별 캠페인 타입별 합산 행 생성
- 기입 조건: `cost > 0 or clicks > 0`
- 수식 열: 월(`=TEXT`), 주차(`=MONTH&INT`)

### `run_daily.py` — 수정
- 네이버 SA 일별 자동 수집 → Google Sheets 기입 통합

### `SETUP_네이버검색광고API.md` — 신규
- 네이버 검색광고 API 셋업 가이드

---

## Google Sheets 시트 구조 — 네이버 SA (A:P)

| 열 | 항목 |
|----|------|
| A | 날짜 |
| B | 총광고비 |
| C | 총클릭 |
| D | 구매완료 전환수 |
| E | 구매완료 전환매출 |
| F | 브검_광고비 |
| G | 브검_클릭 |
| H | 브검_전환 |
| I | 파워링크_광고비 |
| J | 파워링크_클릭 |
| K | 파워링크_전환 |
| L | 쇼검_광고비 |
| M | 쇼검_클릭 |
| N | 쇼검_전환 |
| O | 월 (수식) |
| P | 주차 (수식) |

---

## 백필 결과

| 항목 | 값 |
|------|-----|
| 기간 | 2026-01-23 ~ 2026-04-21 |
| 일수 | 89일 |
| 총광고비 | 7,717,513원 |
| 구매완료 전환수 | 1,508건 |
| 구매완료 전환매출 | 69,144,420원 |

---

## 탐색/진단 스크립트 (삭제됨)
- `probe_naver_campaigns.py` — 캠페인 구조 탐색
- `probe_naver_stats.py` ~ `probe_naver_stats7.py` — stats API 파라미터/필드 테스트
- `probe_naver_ads.py`, `probe_naver_ads2.py` — 소재 단위 API 탐색
- `probe_naver_url.py` — 소재 URL 필드 구조 확인
- `probe_naver_full.py` — 소재 단위 통합 테스트

---

## 해결한 이슈

| 이슈 | 원인 | 해결 |
|------|------|------|
| Invalid Signature (403) | `.hexdigest()` 사용 | `.digest()` + `base64.b64encode()` |
| 캠페인 유형 전부 [기타] | `campaignTp`가 문자열 반환 | `WEB_SITE` 등 문자열 키 추가 |
| stats 400 에러 | `datePreset: 'custom'` 포함 | 파라미터 제거 |
| 구매매출 불일치 | `convAmt`=총전환(모든유형) | `purchaseConvAmt` 사용 |
| 파일 인식 불가 | `.json.json` 이중확장자 | `ren` 명령으로 수정 |
