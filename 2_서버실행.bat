@echo off
chcp 65001 > nul
echo.
echo ====================================
echo   POSCOPE 서버 시작
echo ====================================
echo.
cd /d "%~dp0"
start "" http://127.0.0.1:5000
python app.py
pause
