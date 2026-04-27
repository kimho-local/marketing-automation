@echo off
chcp 949 >nul

REM ================================================
REM  프로젝트 폴더를 사용자 PATH에 추가 (1회 실행)
REM  이후 cmd 어디서든: renk / report / slack 사용 가능
REM ================================================

set "PROJECT=C:\Users\valen\OneDrive\문서\Claude\Projects\valen_brandmarketing_Team1_AI.Assistant"

REM 기존 AutoRun 정리 (이전 시도 잔여)
reg delete "HKCU\Software\Microsoft\Command Processor" /v AutoRun /f >nul 2>&1

REM aliases.cmd 삭제
if exist "%PROJECT%\aliases.cmd" del "%PROJECT%\aliases.cmd"

REM 현재 사용자 PATH 읽기
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "UPATH=%%B"

REM 이미 등록되어 있는지 확인
echo %UPATH% | find /i "%PROJECT%" >nul 2>&1
if %errorlevel%==0 (
    echo  이미 PATH에 등록되어 있습니다.
    goto :done
)

REM PATH에 추가
if defined UPATH (
    setx Path "%UPATH%;%PROJECT%" >nul
) else (
    setx Path "%PROJECT%" >nul
)

:done
echo.
echo  [OK] PATH 등록 완료!
echo  cmd를 새로 열면 어디서든 아래 명령어 사용 가능:
echo.
echo    renk                 프로젝트 폴더 이동
echo    report               어제 보고서 생성
echo    report 2026-04-23    특정 날짜
echo    slack                Slack 발행
echo    slack 2026-04-23     특정 날짜
echo.
pause
