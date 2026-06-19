@echo off
chcp 65001 > nul
echo.
echo ====================================
echo   POSCOPE 크롤러 설치
echo ====================================
echo.
echo Python 버전 확인 중...
python --version
if errorlevel 1 (
    echo.
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 설치 후 다시 실행하세요.
    pause
    exit /b
)
echo.
echo 필요한 라이브러리 설치 중...
cd /d "%~dp0"
pip install -r requirements.txt
echo.
echo ====================================
echo   설치 완료!
echo   이제 2_서버실행.bat을 실행하세요.
echo ====================================
pause
