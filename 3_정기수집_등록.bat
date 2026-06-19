@echo off
chcp 65001 > nul
echo.
echo ====================================
echo   POSCOPE 정기 수집 작업 등록
echo   (Windows 작업 스케줄러에 6시간마다
echo    크롤러를 실행하도록 등록합니다)
echo ====================================
echo.
cd /d "%~dp0"
set TASK_NAME=POSCOPE_AutoCrawl
set PYTHON_EXE=python
set SCRIPT_PATH=%~dp0crawler.py

schtasks /create /tn "%TASK_NAME%" /tr "\"%PYTHON_EXE%\" \"%SCRIPT_PATH%\"" /sc HOURLY /mo 6 /f

if errorlevel 1 (
    echo.
    echo [오류] 작업 등록에 실패했습니다. 관리자 권한으로 다시 실행해보세요.
    pause
    exit /b
)

echo.
echo ====================================
echo   등록 완료!
echo   - 작업 이름: %TASK_NAME%
echo   - 주기: 6시간마다 crawler.py 실행
echo   - 확인/해제: Windows "작업 스케줄러"에서 %TASK_NAME% 검색
echo   - 등록 해제: schtasks /delete /tn "%TASK_NAME%" /f
echo ====================================
pause
