# CHANGELOG — Google Ads 자동화 (2026-04-23)

## 요약
Google Ads API 연동 및 Google Sheets 백필 완료.
gRPC 방식(google-ads 라이브러리) 사용. 36일(3/16~4/20) 데이터 기입.

---

## Google Ads API 연동

### 인증 방식
- OAuth 2.0 + Developer Token (gRPC)
- MCC 계정(5217936160) → 하위 고객 계정(6332033788) 접근
- 라이브러리: `google-ads` Python 패키지 (pip install google-ads)

### REST API 실패 → gRPC 전환
- REST API (`googleads.googleapis.com`) — v16~v19 모든 버전 404 반환
- 원인 미확인 (API 활성화 완료, 토큰 정상, Customer ID 정확)
- gRPC (google-ads 라이브러리) 전환 후 즉시 성공

### 캠페인 타입 enum 매핑
| enum 값 | 문자열 | 한글 |
|---------|--------|------|
| 2 | SEARCH | 검색 |
| 10 | PERFORMANCE_MAX | P-Max |
| 14 | DEMAND_GEN | 디멘드젠 |

### 확인된 캠페인
- `[P-Max]tROAS200` — P-Max
- `[SA] 리엔케이 검색광고` — 검색
- `[디맨드젠] 콜라겐 미드샷 앰플` — 디멘드젠

---

## Google Sheets 기입

### 시트 구조 (META 자사몰과 동일 13열)
```
날짜 | 광고비 | 노출 | 클릭 | 구매 | 매출(전환값) | ROAS(%) | CTR(%) | CPC | CPM | CPA | 월 | 주차
```

### 백필 결과
- 기간: 2026-03-16 ~ 2026-04-20 (36일)
- 총 광고비: 약 1,976,000원
- 전환: 10건 (P-Max 중심)
- Rate Limit 방지: 5행마다 2초 딜레이

---

## Slack 보고서 업로드

### 구현
- `slack_uploader.py` — Slack v2 File Upload API 사용
- User Token(xoxp-) 사용 → 본인 계정으로 업로드 (삭제 가능)
- Google Sheets 링크 자동 첨부

### Slack App
- App명: ReNK-Daily-Report
- Scopes: `files:write`, `files:read`, `chat:write`
- 채널: #팀-브랜드-1파트 (C0A65DK56HL)

---

## 파이프라인 개선사항

### 0행 자동 덮어쓰기
- 네이버 SA D+1~D+2 리포팅 지연 대응
- 기존 행이 0이고 새 데이터 있으면 → UPDATE로 덮어쓰기
- 기존 행에 실제 데이터 있으면 → SKIP

### 카페24 주문 API Fallback
- Dashboard API: 오늘+어제 2일만 반환 (카페24 제한)
- 그 이전 날짜: /admin/orders API로 직접 집계
- 방문자수: API 미제공 → CSV 백필에서만 가능

### 보고서 개선
- 미집행 매체도 0원 섹션 표시 (빈 섹션 숨김 → 0원 표시)
- ROAS 표기: x배 → % 변경 (964.8%)
- Sheets API 429 Rate Limit 자동 재시도 (15초 → 30초 → 60초)

---

## 파일 목록

| 파일 | 역할 | 변경 |
|------|------|------|
| `google_ads_fetcher.py` | Google Ads gRPC 데이터 수집 | REST → gRPC 전환 |
| `slack_uploader.py` | Slack 보고서 파일 업로드 | 신규 |
| `slack_file_cleanup.py` | Slack 파일 조회/삭제 | 신규 |
| `google_sheets_writer.py` | Sheets 기입 (Google Ads 시트 추가) | 0행 덮어쓰기 로직 추가 |
| `cafe24_api_fetcher.py` | 카페24 수집 (주문 API fallback) | Dashboard 한계 대응 |
| `run_daily.py` | 파이프라인 통합 | 무조건 기입 + cp949 인코딩 수정 |
| `generate_daily_report.js` | docx 보고서 생성 | ROAS % 변경, 0원 섹션 표시 |
| `config/renk_google_ads_credentials.json` | Google Ads 인증 | 신규 |
| `config/renk_slack_config.json` | Slack 설정 | 신규 |
| `backfill/backfill_google_ads.py` | Google Ads 시트 백필 | 신규 |
| `docs/guide/광고매체_API_통합_셋업가이드.docx` | 5개 매체 통합 가이드 | 카페24 추가, 작성자 변경 |
