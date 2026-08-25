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
    venv_err="$(python3 -m venv .venv 2>&1)" || {
        echo "$venv_err" >&2
        if echo "$venv_err" | grep -qi "ensurepip" && command -v apt-get >/dev/null 2>&1; then
            # Debian/Ubuntu split ensurepip out of the base python3 package
            # into a version-specific one (e.g. python3.12-venv). Prefer the
            # exact name Python's own error suggests; otherwise derive it
            # from the running interpreter's version, falling back to the
            # generic meta-package if that specific install fails.
            venv_pkg="$(echo "$venv_err" | grep -oE 'python3\.[0-9]+-venv' | head -n1 || true)"
            if [ -z "$venv_pkg" ]; then
                venv_pkg="python3.$(python3 -c 'import sys; print(sys.version_info[1])')-venv"
            fi
            echo "Missing the $venv_pkg system package -- installing it and retrying..."
            rm -rf .venv
            sudo apt-get update || true
            sudo apt-get install -y "$venv_pkg" || sudo apt-get install -y python3-venv
            python3 -m venv .venv
        else
            exit 1
        fi
    }
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

# 4) Launch it now, so the install is a single "run this script and you're
#    in the app" step rather than requiring a second trip to the app menu.
if [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
    echo "Launching ScreenWatch..."
    nohup "$REPO_DIR/.venv/bin/screenwatch" >/dev/null 2>&1 &
    disown
else
    echo "No graphical display detected -- open ScreenWatch from your"
    echo "application menu once you're on the desktop."
fi
