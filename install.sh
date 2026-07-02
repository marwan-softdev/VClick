#!/usr/bin/env bash
# One-shot setup for ScreenWatch on Debian/Ubuntu-like systems.
# Creates a local virtualenv and installs the Python dependencies.
# Tkinter comes from the system package 'python3-tk'.
set -euo pipefail
cd "$(dirname "$0")"

echo "== ScreenWatch installer =="

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

# 2) Create a virtualenv and install the Python deps.
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

echo
echo "Done. Start ScreenWatch with:  ./run.sh"
echo "Diagnostics:                   ./run.sh --check"
