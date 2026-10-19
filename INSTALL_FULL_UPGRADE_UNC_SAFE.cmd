@echo off
setlocal EnableExtensions
pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
  echo STOPPED: Could not access the folder containing this installer.
  pause
  exit /b 1
)
echo Commercial MTM Full Upgrade - New Deals KPI
echo Working folder: %CD%
echo.
if not exist "local_date_app.py" (
  echo STOPPED: local_date_app.py was not found beside this installer.
  goto :fail
)
if not exist "local_date_app_FULL_UPGRADE.py" (
  echo STOPPED: local_date_app_FULL_UPGRADE.py was not found beside this installer.
  goto :fail
)
if not exist "workspace\workspace.js" (
  echo STOPPED: workspace\workspace.js was not found.
  goto :fail
)
findstr /c:"DealID" "workspace\workspace.js" >nul || (
  echo STOPPED: DealID was not found in workspace.js.
  goto :fail
)
findstr /c:"NewDealCurveShift" "workspace\workspace.js" >nul || (
  echo STOPPED: NewDealCurveShift was not found in workspace.js.
  goto :fail
)
if not exist "local_date_app_BEFORE_NEW_DEALS.py" (
  copy /y "local_date_app.py" "local_date_app_BEFORE_NEW_DEALS.py" >nul || goto :fail
  echo Created rollback copy: local_date_app_BEFORE_NEW_DEALS.py
) else (
  echo Rollback copy already exists; it was not overwritten.
)
py -m py_compile "local_date_app_FULL_UPGRADE.py"
if errorlevel 1 goto :fail
copy /y "local_date_app_FULL_UPGRADE.py" "local_date_app.py" >nul
if errorlevel 1 goto :fail
py "local_date_app.py" --check
if errorlevel 1 goto :rollback
echo.
echo SUCCESS: Full upgrade installed and preflight passed.
echo workspace.js, local_date_selections.json, archive files, and source data were not modified.
popd
pause
exit /b 0
:rollback
echo.
echo Preflight failed. Restoring local_date_app_BEFORE_NEW_DEALS.py.
copy /y "local_date_app_BEFORE_NEW_DEALS.py" "local_date_app.py" >nul
:fail
echo.
echo INSTALL FAILED. Review the message above.
popd
pause
exit /b 1
