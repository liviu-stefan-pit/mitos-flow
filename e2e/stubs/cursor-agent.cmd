@echo off
REM Phase 31 — Cursor CLI stub for Playwright / CI (Windows).
REM Handles capability probe flags and a deterministic success spawn.
setlocal EnableExtensions

if /I "%~1"=="--version" (
  echo 1.2.3
  exit /b 0
)

if /I "%~1"=="--help" (
  echo Usage: agent [options]
  echo   --print
  echo   --output-format ^<text^|json^>
  echo   --workspace ^<path^>
  echo   --model ^<id^>
  echo   --list-models
  echo   --trust
  echo   --force
  echo   --api-key ^<key^>
  exit /b 0
)

if /I "%~1"=="--list-models" (
  echo composer-2.5
  echo composer-2.5-fast
  exit /b 0
)

REM Default: pretend a successful agent run. Stdin is ignored.
echo STUB_OK:Hello from input
exit /b 0
