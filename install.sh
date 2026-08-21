#!/usr/bin/env bash
# One-shot setup for ScreenWatch on Linux (Debian/Ubuntu/Fedora/Arch).
# Creates a local virtualenv, installs ScreenWatch into it, and registers a
# launcher icon in the desktop's application menu — so afterwards you can
# start ScreenWatch by clicking its icon, with no terminal required.
set -euo pipefail
cd "$(dirname "$0")"
REPO_DIR="$(pwd)"

echo "== ScreenWatch installer (2026-08-21) =="

# 1) Make sure system Tkinter is present (can't be pip-installed reliably).
if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    echo "Tkinter is missing. Attempting to install 'python3-tk'..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update && sudo apt-get install -y python3-tk
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y python3-tkinter
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --needed tk
    else
        echo "!! Please install the Tkinter package for your distro manually."
    fi
fi

# 2) Create a virtualenv and install ScreenWatch (editable, so the app keeps
#    reading its source/assets straight from this checkout).
# A previous run may have left an incomplete .venv (interrupted, disk full,
# etc.) -- one that exists but has no working interpreter. Detect that and
# start fresh rather than fail trying to activate/use a broken environment.
if [ -d ".venv" ] && { [ ! -f ".venv/bin/activate" ] || [ ! -x ".venv/bin/python" ]; }; then
    echo "Found an incomplete .venv from an earlier install attempt -- removing it and starting fresh."
    rm -rf .venv
fi
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -e .
deactivate

# 3) Register a launcher icon in the application menu (GNOME/KDE/XFCE/etc.
#    all read *.desktop files from ~/.local/share/applications).
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
sed \
    -e "s|__EXEC__|$REPO_DIR/.venv/bin/screenwatch|" \
    -e "s|__ICON__|$REPO_DIR/screenwatch/assets/icon.png|" \
    "$REPO_DIR/assets/screenwatch.desktop" > "$APPS_DIR/screenwatch.desktop"
chmod +x "$APPS_DIR/screenwatch.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

echo
echo "Done! ScreenWatch is installed."
echo "  - Open it from your application menu / app list (search \"ScreenWatch\")."
echo "  - Or from a terminal:  ./run.sh"
echo "  - Diagnostics:         ./run.sh --check"
