@echo off
setlocal
REM Builds a standalone ScreenWatch.exe with PyInstaller: one portable file
REM with its own bundled Python, Tkinter, and dependencies -- no separate
REM Python install needed, and no console window when it's launched.
REM Must be run on Windows (PyInstaller cannot cross-compile from another OS).
cd /d "%~dp0..\.."

echo == ScreenWatch .exe builder ==

python -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    exit /b 1
)
pip install -e .
if errorlevel 1 (
    echo Failed to install ScreenWatch's dependencies.
    exit /b 1
)
pip install pyinstaller
if errorlevel 1 (
    echo Failed to install PyInstaller.
    exit /b 1
)

pyinstaller --onefile --windowed --noconfirm --name ScreenWatch --icon screenwatch\assets\icon.ico --add-data "screenwatch\assets;screenwatch\assets" --hidden-import mss.windows --hidden-import pynput.mouse._win32 --hidden-import pynput.keyboard._win32 --distpath packaging\windows-exe\dist --workpath packaging\windows-exe\build --specpath packaging\windows-exe packaging\windows-exe\entrypoint.py
if errorlevel 1 (
    echo PyInstaller build failed.
    exit /b 1
)

echo.
echo Done. The executable was written to:
echo   packaging\windows-exe\dist\ScreenWatch.exe
endlocal
