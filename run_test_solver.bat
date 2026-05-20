@echo off
setlocal
cd /d "%~dp0EDUX-TEST-SOLVER"
pytest -s --headed --browser chromium
endlocal
