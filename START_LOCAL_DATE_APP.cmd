@echo off
setlocal

if not exist "%~dp0local_date_app.py" (
    echo ERROR: local_date_app.py was not found beside this launcher.
    pause
    exit /b 1
)

if not exist "%~dp0snapshot_manager.py" (
    echo ERROR: snapshot_manager.py was not found.
    echo Put these files in the main project folder beside workspace.
    pause
    exit /b 1
)

echo Checking Python syntax...
py -m py_compile "%~dp0local_date_app.py"

if errorlevel 1 (
    echo.
    echo ERROR: Python syntax check failed.
    echo The application was not started.
    pause
    exit /b 1
)

echo Checking project files...
py "%~dp0local_date_app.py" --check

if errorlevel 1 (
    echo.
    echo ERROR: Project preflight failed.
    echo Review the message above.
    pause
    exit /b 1
)

echo Starting local dashboard...
echo Keep this window open while using the application.
echo.

py "%~dp0local_date_app.py"
set "APP_EXIT=%ERRORLEVEL%"

echo.
echo Local application stopped.
if not "%APP_EXIT%"=="0" echo Review the error message above.
pause

exit /b %APP_EXIT%