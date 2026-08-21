#!/usr/bin/env bash
# Builds a ScreenWatch AppImage: a single, portable executable file that
# needs no install step — download it, mark it executable once, double-click
# (or run it) from then on. No root, no system Python packages required.
#
# Requires real internet access to GitHub (api.github.com + release assets,
# for the base Python-AppImage runtime) and PyPI, for the Python deps.
set -euo pipefail
cd "$(dirname "$0")"
APPIMAGE_DIR="$(pwd)"

echo "== ScreenWatch AppImage builder =="

if ! python3 -c "import python_appimage" >/dev/null 2>&1; then
    echo "Installing python-appimage..."
    pip3 install --quiet --upgrade python-appimage
fi

echo "Building AppImage (this downloads a base Python runtime + installs deps)..."
python3 -m python_appimage build app \
    --python-version 3.11 \
    "$APPIMAGE_DIR"

echo
echo "Done. The AppImage was written to:"
ls -1 "$APPIMAGE_DIR"/ScreenWatch-*.AppImage 2>/dev/null || echo "  (check the output above for the exact filename/location)"
echo
echo "To use it: chmod +x the file (or tick 'Allow executing as program' in"
echo "your file manager's Properties dialog), then double-click it. No"
echo "install step, no root, and it can be moved/copied anywhere."
