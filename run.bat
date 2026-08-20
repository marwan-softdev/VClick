@echo off
REM Convenience launcher for ScreenWatch.
REM Uses .venv if it exists (created by install.bat), otherwise system Python.
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\screenwatch.exe" (
    ".venv\Scripts\screenwatch.exe" %*
    goto :eof
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m screenwatch %*
    goto :eof
)

python -m screenwatch %*
