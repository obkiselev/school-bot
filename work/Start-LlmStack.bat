@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%start-llm-stack.ps1"

if not exist "%PS_SCRIPT%" (
  echo [ERROR] Script not found: %PS_SCRIPT%
  pause
  exit /b 1
)

powershell -ExecutionPolicy Bypass -File "%PS_SCRIPT%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo [OK] LLM stack check passed.
) else (
  echo [FAIL] LLM stack check failed. Fix issues and run again.
)

pause
exit /b %EXIT_CODE%
