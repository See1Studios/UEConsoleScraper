@echo off
echo [*] UE Console Variables Scraper 환경 설정 중...

set VENV_DIR=%~dp0.venv

if not exist "%VENV_DIR%" (
    echo [*] 가상환경 생성 중...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [!] 가상환경 생성 실패. Python이 설치되어 있는지 확인하세요.
        pause
        exit /b 1
    )
)

echo [*] 패키지 설치 중...
call "%VENV_DIR%\Scripts\activate.bat"
pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [!] 패키지 설치 실패.
    pause
    exit /b 1
)

echo [*] Playwright 브라우저(Chromium) 설치 중...
playwright install chromium
if errorlevel 1 (
    echo [!] Playwright 브라우저 설치 실패.
    pause
    exit /b 1
)

echo.
echo [완료] 설치가 완료되었습니다.
echo.
echo 사용법:
echo   .venv\Scripts\activate
echo   python scrape_cvars.py
echo   python scrape_cvars.py --version 5.6 --lang ko --output cvars.json
echo   python scrape_cvars.py --dump-html
echo.
pause
