@echo off
setlocal EnableExtensions
if not exist "%~dp0workspace\data.js" (
  echo No published data. Run BUILD_WORKSPACE.cmd first.
  pause
  exit /b 1
)
start "" "%~dp0workspace\index.html"
