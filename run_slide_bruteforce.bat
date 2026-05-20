@echo off
setlocal
cd /d "%~dp0EDUX-SLIDE-BRUTEFORCE"
pytest -s --headed --browser chromium
endlocal
