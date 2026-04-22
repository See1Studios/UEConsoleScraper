@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo.
echo [*] UE Console Variables Scraper 환경 설정
echo.

set VENV_DIR=%~dp0.venv

REM Python 설치 확인
py --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python을 찾을 수 없습니다.
    echo.
    echo 해결 방법:
    echo 1. python.org 에서 Python 설치
    echo 2. 설치 시 "Add Python to PATH" 반드시 체크
    echo 3. 새 터미널을 열고 다시 실행
    echo.
    pause
    exit /b 1
)

REM 가상환경 생성
if not exist "%VENV_DIR%" (
    echo [*] 가상환경 생성 중...
    py -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] 가상환경 생성 실패
        pause
        exit /b 1
    )
)

REM 패키지 설치
echo [*] 패키지 설치 중...
call "%VENV_DIR%\Scripts\activate.bat"
pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo [ERROR] 패키지 설치 실패
    pause
    exit /b 1
)

REM Playwright 설치 (시스템 Edge가 있으면 생략)
set EDGE_EXE=
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set EDGE_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe
if not defined EDGE_EXE if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set EDGE_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe

if defined EDGE_EXE (
    echo [*] 시스템 Edge 감지: !EDGE_EXE!
    echo [*] Playwright Edge 다운로드를 건너뜁니다.
) else (
    echo [*] Edge 미감지 - Playwright Edge 채널 설치 중...
    playwright install msedge
    if errorlevel 1 (
        echo [ERROR] Playwright 설치 실패
        pause
        exit /b 1
    )
)

echo.
echo [완료] 설치가 완료되었습니다!
echo.
echo 사용 방법:
echo   .venv\Scripts\activate
echo   python ue_console_ref.py  ^(GUI 실행^)
echo   python ue_console_ref_cli.py --help
echo   python ue_console_ref_cli.py --target cvars --version 5.6 --lang ko
echo.
pause
