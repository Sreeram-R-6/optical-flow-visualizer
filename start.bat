@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 scripts\run_dev.py %*
) else (
  python scripts\run_dev.py %*
)
if errorlevel 1 (
  echo.
  echo Startup failed. Read the message above.
  pause
)
