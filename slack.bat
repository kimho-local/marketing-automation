@echo off
cd /d "%~dp0"
if "%~1"=="" (py run_daily.py --slack) else (py run_daily.py --date %1 --slack)
pause
