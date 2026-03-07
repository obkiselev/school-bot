@echo off
set SCRIPT_DIR=%~dp0
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start-llm-reverse-tunnel.ps1"
