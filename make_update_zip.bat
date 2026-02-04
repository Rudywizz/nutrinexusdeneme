@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
set "OUT_ZIP=%SCRIPT_DIR%nutrinexus_updates.zip"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Resolve-Path '%SCRIPT_DIR%').Path;" ^
  "$files = @(" ^
  "  (Join-Path $root 'src\\main.py')," ^
  "  (Join-Path $root 'src\\ui\\screens\\settings.py')," ^
  "  (Join-Path $root 'src\\ui\\theme\\style.qss')," ^
  "  (Join-Path $root 'src\\ui\\theme\\palette.py')," ^
  "  (Join-Path $root 'apply_settings_layout_update_onefile.bat')" ^
  ");" ^
  "$missing = $files | Where-Object { -not (Test-Path $_) };" ^
  "if ($missing.Count -gt 0) {" ^
  "  Write-Error ('Missing files: ' + ($missing -join ', '));" ^
  "  exit 1;" ^
  "}" ^
  "Compress-Archive -Force -Path $files -DestinationPath (Join-Path $root 'nutrinexus_updates.zip');" ^
  "Write-Host 'Update zip created:' (Join-Path $root 'nutrinexus_updates.zip');"

if %ERRORLEVEL% NEQ 0 (
  echo Failed to create update zip.
  exit /b 1
)

exit /b 0
