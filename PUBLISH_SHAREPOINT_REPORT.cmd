@echo off
setlocal EnableExtensions
pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
  echo STOPPED: Cannot access the project folder.
  pause
  exit /b 1
)
py "publish_sharepoint_report.py"
set "RESULT=%ERRORLEVEL%"
popd
pause
exit /b %RESULT%
