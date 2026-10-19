@echo off
setlocal
py "%~dp0daily_source_update.py" build
if errorlevel 1 (
 echo Daily refresh stopped. Review the message above.
 pause
 exit /b 1
)
pause
