@echo off
setlocal EnableExtensions
rem PUSHD supports UNC network shares; absolute paths below do not depend on CWD.
pushd "%~dp0"
if errorlevel 1 (
  echo Could not access the workspace folder. Check network connectivity.
  pause
  exit /b 1
)
set "SOURCE=O:\SEM\Common\Endur\AutoFiles\RISK\TPORT_MTM_COMMERCIAL_MM-DD-YY_.xlsb"
if not "%~1"=="" set "SOURCE=%~1"
py -c "import pyxlsb" >nul 2>&1
if errorlevel 1 (
  echo Python or pyxlsb is unavailable. In your VS Code terminal run:
  echo py -m pip install pyxlsb
  popd
  pause
  exit /b 1
)
echo Reading the source workbook. Source files are not modified.
echo Progress is printed every 25,000 dated records.
py "%~dp0build_workspace.py" --file "%SOURCE%" --out "%~dp0workspace"
if errorlevel 1 (
  echo BUILD FAILED. No new dashboard has been opened. Review the message above.
  popd
  pause
  exit /b 1
)
start "" "%~dp0workspace\index.html"
popd
echo Workspace built and opened.
pause
exit /b 0
