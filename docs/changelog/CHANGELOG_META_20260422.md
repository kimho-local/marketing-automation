# Re:NK 자동화 파이프라인 변경 내역 (2026-04-22)

## 변경 요약
Google Sheets 아카이빙 시스템 구축 및 백필 완료 (META 자사몰 + 스마트스토어)

---

## 신규 파일

### `backfill_sheets.py`
- Meta API → Google Sheets 과거 데이터 일괄 기입 (배치 방식)
- `--own` / `--ss` / `--all` 플래그로 매체 선택
- `--dry-run`으로 미리보기 지원
- 데이터 없는 날짜도 0으로 채워서 빈 날 없이 기입

### `google_sheets_writer.py`
- Google Sheets API 연동 (서비스 계정 JWT 인증)
- 매체별 4개 시트 자동 생성 + 헤더 기입 (`--init`)
- 중복 방지 (날짜 기준 체크)
- `OVERWRITE` 모드로 서식 유지

---

## 수정 파일

### `google_sheets_writer.py` — 서식 및 수식 관련
- ROAS(%), CTR(%): `ROUND(..., 2)` 소수점 2자리
- CPC, CPM, CPA: `ROUND(..., 0)` 정수
- 전체 숫자 열: `#,##0` 천 단위 콤마 서식
- 날짜 열: `yyyy-mm-dd` 서식
- 전체 셀 가운데 정렬
- 월 열 추가: `=TEXT(A{n},"YYYY-MM")`
- 주차 열 추가: `=MONTH(A{n})&"월-"&INT((DAY(A{n})-1)/7)+1&"주차"`
- META 스마트스토어: CPAS구매(E) → CPAS전환값(F) 순서 수정 (자사몰과 통일)

### `실행_윈도우.bat`
- UTF-8 BOM 제거 (Windows cmd 파싱 오류 해결)
- 한국어 echo → 영어로 교체
- CRLF 줄바꿈 적용

### `cafe24_api_fetcher.py` / `cafe24_get_token.py`
- TOKEN_FILE: `cafe24_token.json` → `renk_cafe24_token.json`

### `naver_api_fetcher.py`
- CREDENTIALS_FILE: `renk_naver_credentials.json`

### `google_ads_fetcher.py`
- CREDENTIALS_FILE: `renk_google_ads_credentials.json`

---

## 시트 구조 (최종)

### META 자사몰 (A~M)
날짜 | 광고비 | 노출 | 클릭 | 구매 | 매출(전환값) | ROAS(%) | CTR(%) | CPC | CPM | CPA | 월 | 주차

### META 스마트스토어 (A~L)
날짜 | 광고비 | 노출 | 클릭 | CPAS구매 | CPAS전환값 | ROAS(%) | CTR(%) | CPC | CPM | 월 | 주차

### 네이버 SA (A~P)
날짜 | 총광고비 | 총클릭 | 구매완료 전환수 | 구매완료 전환매출 | 브검_광고비 | 브검_클릭 | 브검_전환 | 파워링크_광고비 | 파워링크_클릭 | 파워링크_전환 | 쇼검_광고비 | 쇼검_클릭 | 쇼검_전환 | 월 | 주차

### 카페24 커머스 (A~K)
날짜 | 순매출 | 주문건수 | 구매자수 | 객단가 | 상품금액 | 할인 | 쿠폰 | 배송비 | 월 | 주차

---

## 백필 완료 현황
- META 자사몰: 2026-02-19 ~ 2026-04-20 ✅ 완료
- META 스마트스토어: 2026-01-02 ~ 2026-04-20 ✅ 완료
- 카페24 커머스: 2026-02-19 ~ 2026-04-20 ✅ 완료
- 네이버 SA: 2026-01-23 ~ 2026-04-21 ✅ 완료
