@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "SOURCE_DIR=%SCRIPT_DIR%tools\design_updates"
set "TARGET_THEME_DIR=%SCRIPT_DIR%src\ui\theme"

if not exist "%SOURCE_DIR%" (
  echo Missing source folder: %SOURCE_DIR%
  exit /b 1
)

if not exist "%TARGET_THEME_DIR%" (
  echo Missing target folder: %TARGET_THEME_DIR%
  exit /b 1
)

copy /Y "%SOURCE_DIR%\style.qss" "%TARGET_THEME_DIR%\style.qss" >nul
if %ERRORLEVEL% NEQ 0 (
  echo Failed to update style.qss
  exit /b 1
)

copy /Y "%SOURCE_DIR%\palette.py" "%TARGET_THEME_DIR%\palette.py" >nul
if %ERRORLEVEL% NEQ 0 (
  echo Failed to update palette.py
  exit /b 1
)

echo Design updates applied successfully.
exit /b 0
