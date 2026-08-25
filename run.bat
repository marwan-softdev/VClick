@echo off
REM Convenience launcher for VClick.
REM Uses .venv if it exists (created by install.bat), otherwise system Python.
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\vclick.exe" (
    ".venv\Scripts\vclick.exe" %*
    goto :eof
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m vclick %*
    goto :eof
)

python -m vclick %*
