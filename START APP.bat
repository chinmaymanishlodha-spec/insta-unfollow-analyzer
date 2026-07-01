@echo off
setlocal
cd /d "%~dp0"
title Who doesn't follow me back? - Analyzer

echo ==================================================
echo    Instagram "Who doesn't follow me back?"
echo ==================================================
echo.

REM --- Check Python is available -------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python was not found on your PATH.
  echo Install Python 3 from https://www.python.org/downloads/ ^(tick "Add to PATH"^),
  echo then double-click this file again.
  echo.
  pause
  exit /b 1
)

REM --- Install requirements on first run ------------------------------------
python -c "import streamlit, pandas" >nul 2>&1
if errorlevel 1 (
  echo First run: installing required packages, please wait...
  python -m pip install -r requirements.txt
  echo.
)

echo Starting the app. Two ways to open it:
echo.
echo    On THIS PC:        http://localhost:8770
echo    On OTHER devices:  http://YOUR-PC-IP:8770   ^(same Wi-Fi^)
echo.
echo    Find YOUR-PC-IP by running "ipconfig" and using the IPv4 Address.
echo.
echo Keep this window OPEN while using the app. Close it to stop the app.
echo ==================================================
echo.

python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8770

echo.
echo The app has stopped.
pause
