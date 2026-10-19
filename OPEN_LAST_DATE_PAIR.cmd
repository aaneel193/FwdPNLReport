@echo off
setlocal
py "%~dp0snapshot_manager.py" open-last
if errorlevel 1 (
 echo.
 echo Review the message above. Existing daily dashboard was not overwritten.
 pause
 exit /b 1
)
pause
