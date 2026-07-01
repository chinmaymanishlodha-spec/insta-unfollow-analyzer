@echo off
setlocal enabledelayedexpansion
title Stop - Who doesn't follow me back?

echo ==================================================
echo    Stopping the analyzer app (port 8770)...
echo ==================================================
echo.

set FOUND=0
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8770" ^| findstr LISTENING') do (
  taskkill /PID %%P /F >nul 2>&1
  if not errorlevel 1 set FOUND=1
)

if "!FOUND!"=="1" (
  echo Done - the app has been stopped.
) else (
  echo Nothing was running on port 8770 ^(app already stopped^).
)

echo.
pause
