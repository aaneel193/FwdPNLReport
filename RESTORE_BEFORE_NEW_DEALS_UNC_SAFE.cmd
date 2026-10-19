@echo off
setlocal EnableExtensions
pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
  echo STOPPED: Could not access this folder.
  pause
  exit /b 1
)
if not exist "local_date_app_BEFORE_NEW_DEALS.py" (
  echo STOPPED: local_date_app_BEFORE_NEW_DEALS.py was not found.
  popd
  pause
  exit /b 1
)
copy /y "local_date_app_BEFORE_NEW_DEALS.py" "local_date_app.py" >nul
if errorlevel 1 goto :fail
py -m py_compile "local_date_app.py"
if errorlevel 1 goto :fail
echo Rollback restored successfully.
popd
pause
exit /b 0
:fail
echo RESTORE FAILED. Review the message above.
popd
pause
exit /b 1
