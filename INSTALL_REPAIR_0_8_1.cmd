@echo off
setlocal EnableExtensions
pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
  echo STOPPED: Cannot access the project folder.
  pause
  exit /b 1
)
py "repair_0_8_1_install.py" install
set "RESULT=%ERRORLEVEL%"
popd
pause
exit /b %RESULT%
