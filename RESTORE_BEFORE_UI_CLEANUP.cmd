@echo off
setlocal
cd /d "%~dp0"
if not exist "local_date_app_BEFORE_UI_CLEANUP.py" (
  echo STOPPED: rollback file not found.
  pause
  exit /b 1
)
copy /y "local_date_app_BEFORE_UI_CLEANUP.py" "local_date_app.py" >nul || exit /b 1
py -m py_compile "local_date_app.py" || exit /b 1
echo Rollback restored successfully.
pause
