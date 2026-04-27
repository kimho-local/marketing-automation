@echo off
cd /d "%~dp0"

echo ============================================
echo  Re:NK Daily Pipeline v3
echo  All Media Collect + Sheets + DOCX Report
echo ============================================
echo.

REM Install docx library (first run only)
if not exist "node_modules\docx" (
    echo [SETUP] Installing docx library...
    npm install docx --silent
    echo.
)

REM Run pipeline
py run_daily.py %*

echo.
echo ============================================
echo  Done! Check reports folder for DOCX report
echo ============================================
pause
