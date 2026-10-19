@echo off
setlocal EnableExtensions
rem Absolute paths support UNC shares without relying on CMD's current directory.
py "%~dp0apply_visual_redesign.py" --open
if errorlevel 1 (
  echo.
  echo The visual patch was not applied. Read the message above.
  echo These patch files belong in the same main folder as OPEN_WORKSPACE.cmd.
  pause
  exit /b 1
)
echo.
echo Use OPEN_REDESIGNED.cmd to open the new layout next time.
pause
