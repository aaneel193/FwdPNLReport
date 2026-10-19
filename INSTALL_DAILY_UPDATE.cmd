@echo off
setlocal
py "%~dp0daily_source_update.py" install
if errorlevel 1 goto :fail
py "%~dp0daily_source_update.py" configure
if errorlevel 1 goto :fail
echo.
echo Installed. Use BUILD_DAILY_WORKSPACE.cmd for future refreshes.
pause
exit /b 0
:fail
echo Review the message above. No source workbook was modified.
pause
exit /b 1
