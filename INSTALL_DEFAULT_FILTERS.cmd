@echo off
setlocal
py "%~dp0install_default_filters.py"
if errorlevel 1 echo Review the message above.
pause
