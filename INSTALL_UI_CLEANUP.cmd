@echo off
setlocal
cd /d "%~dp0"
echo Commercial MTM controlled UI cleanup installer
echo.
if not exist "local_date_app.py" (
  echo STOPPED: local_date_app.py was not found in this folder.
  pause
  exit /b 1
)
if not exist "local_date_app_UI_CLEANUP.py" (
  echo STOPPED: local_date_app_UI_CLEANUP.py was not found in this folder.
  pause
  exit /b 1
)
if not exist "local_date_app_BEFORE_UI_CLEANUP.py" (
  copy /y "local_date_app.py" "local_date_app_BEFORE_UI_CLEANUP.py" >nul || goto :fail
  echo Created rollback copy: local_date_app_BEFORE_UI_CLEANUP.py
) else (
  echo Rollback copy already exists; it was not overwritten.
)
py -m py_compile "local_date_app_UI_CLEANUP.py" || goto :fail
copy /y "local_date_app_UI_CLEANUP.py" "local_date_app.py" >nul || goto :fail
py "local_date_app.py" --check || goto :rollback
echo.
echo SUCCESS: UI cleanup installed and preflight passed.
echo Existing launcher, archive, workspace files, and local_date_selections.json were not changed.
pause
exit /b 0
:rollback
echo Preflight failed. Restoring rollback copy.
copy /y "local_date_app_BEFORE_UI_CLEANUP.py" "local_date_app.py" >nul
goto :fail
:fail
echo.
echo INSTALL FAILED. Review the message above. Your rollback copy is available.
pause
exit /b 1
