@echo off
setlocal enabledelayedexpansion
REM One-shot setup for ScreenWatch on Windows.
REM Creates a local virtual environment, installs ScreenWatch into it, and
REM adds a Start Menu (and Desktop) shortcut with a proper icon -- so
REM afterwards you can launch ScreenWatch by clicking it, no terminal needed.

set "REPO_DIR=%~dp0"
if "%REPO_DIR:~-1%"=="\" set "REPO_DIR=%REPO_DIR:~0,-1%"
cd /d "%REPO_DIR%"

echo == ScreenWatch installer ==

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python was not found on PATH.
    echo Install it from https://www.python.org/downloads/windows/
    echo and make sure to tick "Add python.exe to PATH" during setup.
    echo ^(Tkinter and pip are included automatically by that installer --
    echo  nothing extra to install on Windows.^)
    exit /b 1
)

REM A previous run may have left an incomplete .venv (interrupted, disk full,
REM etc.) -- one that exists but has no working interpreter. Detect that and
REM start fresh rather than fail trying to use a broken environment.
if exist ".venv" if not exist ".venv\Scripts\python.exe" (
    echo Found an incomplete .venv from an earlier install attempt -- removing it and starting fresh.
    rmdir /s /q ".venv"
)

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create the virtual environment.
        exit /b 1
    )
)

echo Installing ScreenWatch and its dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\pip.exe" install -e .
if errorlevel 1 (
    echo Installation failed -- see the error above.
    exit /b 1
)

echo Creating a Start Menu shortcut...
set "TARGET=%REPO_DIR%\.venv\Scripts\screenwatch.exe"
set "ICON=%REPO_DIR%\screenwatch\assets\icon.ico"
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\ScreenWatch.lnk"
set "DESKTOP=%USERPROFILE%\Desktop\ScreenWatch.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$s = $ws.CreateShortcut('%STARTMENU%');" ^
    "$s.TargetPath = '%TARGET%';" ^
    "$s.IconLocation = '%ICON%';" ^
    "$s.WorkingDirectory = '%REPO_DIR%';" ^
    "$s.Description = 'Watch a screen area and click when it changes';" ^
    "$s.Save()"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell;" ^
    "$s = $ws.CreateShortcut('%DESKTOP%');" ^
    "$s.TargetPath = '%TARGET%';" ^
    "$s.IconLocation = '%ICON%';" ^
    "$s.WorkingDirectory = '%REPO_DIR%';" ^
    "$s.Description = 'Watch a screen area and click when it changes';" ^
    "$s.Save()"

echo.
echo Done! ScreenWatch is installed.
echo   - Open it from the Start Menu (search "ScreenWatch"), or the new
echo     desktop icon -- no console window will appear.
echo   - Or from a terminal:  run.bat
echo   - Diagnostics:         run.bat --check
endlocal
