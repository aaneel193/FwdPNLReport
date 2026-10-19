@echo off
setlocal EnableExtensions

rem pushd maps a UNC folder to a temporary drive letter, unlike cd /d.
pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
  echo STOPPED: Could not access the folder containing this installer.
  echo Copy the cleanup files into the project folder and try again.
  pause
  exit /b 1
)

echo Commercial MTM controlled UI cleanup installer - UNC safe
echo Working folder: %CD%
echo.

if not exist "local_date_app.py" (
  echo STOPPED: local_date_app.py was not found beside this installer.
  goto :fail
)
if not exist "local_date_app_UI_CLEANUP.py" (
  echo STOPPED: local_date_app_UI_CLEANUP.py was not found beside this installer.
  goto :fail
)

if not exist "local_date_app_BEFORE_UI_CLEANUP.py" (
  copy /y "local_date_app.py" "local_date_app_BEFORE_UI_CLEANUP.py" >nul || goto :fail
  echo Created rollback copy: local_date_app_BEFORE_UI_CLEANUP.py
) else (
  echo Rollback copy already exists; it was not overwritten.
)

py -m py_compile "local_date_app_UI_CLEANUP.py"
if errorlevel 1 goto :fail

copy /y "local_date_app_UI_CLEANUP.py" "local_date_app.py" >nul
if errorlevel 1 goto :fail

py "local_date_app.py" --check
if errorlevel 1 goto :rollback

echo.
echo SUCCESS: UI cleanup installed and preflight passed.
echo Existing launcher, archive, workspace files, and local_date_selections.json were not changed.
popd
pause
exit /b 0

:rollback
echo.
echo Preflight failed. Restoring rollback copy.
copy /y "local_date_app_BEFORE_UI_CLEANUP.py" "local_date_app.py" >nul

:fail
echo.
echo INSTALL FAILED. No intentional changes were made outside local_date_app.py and its rollback copy.
popd
pause
exit /b 1
