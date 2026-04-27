# CHANGELOG — 파이프라인 운영 개선 (2026-04-27)

## 요약
Slack 발행 분리, CMD 단축 명령어 등록으로 일일 운영 효율 개선.

---

## 1. Slack 발행 분리 (run_daily.py)

### 변경 파일
- `run_daily.py` — `--slack` CLI 플래그 추가, `post_to_slack()` 함수 신규

### 변경 내용
- 기존: 파이프라인 실행 시 Slack 발행이 자동 포함 (분리 불가)
- 변경: `--slack` 플래그로 Slack 발행만 단독 실행 가능

### 사용법
```bash
py run_daily.py --date 2026-04-23           # 보고서만 생성
py run_daily.py --date 2026-04-23 --slack   # Slack 발행만 실행
```

### 동작 방식
1. `--slack` 모드 진입 시 `reports/` 폴더에서 해당 날짜 docx 파일 검색
2. `slack_uploader.py`로 파일 업로드 (v2 API)
3. Google Sheets 링크 자동 첨부 (설정 시)

---

## 2. CMD 단축 명령어 등록

### 신규 파일
- `renk.bat` — 프로젝트 폴더로 이동 (`cd /d 경로`)
- `report.bat` — `py run_daily.py` 실행 (날짜 인자 전달)
- `slack.bat` — `py run_daily.py --slack` 실행 (날짜 인자 전달)
- `setup_alias.bat` — 프로젝트 폴더를 사용자 PATH에 등록

### 사용법 (CMD 어디서든)
```cmd
renk                    # 프로젝트 폴더로 이동
report 2026-04-23       # 보고서 생성
slack 2026-04-23        # Slack 발행
```

### 셋업
```cmd
py setup_alias.bat      # PATH 등록 (최초 1회)
```
※ bat 파일은 CP949 인코딩으로 생성 (Windows CMD 한글 호환)

---

## 파일 변경 요약

| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `run_daily.py` | 수정 | `--slack` 플래그 + `post_to_slack()` 추가 |
| `renk.bat` | 신규 | 프로젝트 폴더 이동 단축 명령어 |
| `report.bat` | 신규 | 보고서 생성 단축 명령어 |
| `slack.bat` | 신규 | Slack 발행 단축 명령어 |
| `setup_alias.bat` | 신규 | PATH 등록 스크립트 |
