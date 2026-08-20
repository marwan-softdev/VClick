#!/usr/bin/env bash
# Builds a ScreenWatch AppImage: a single, portable executable file that
# needs no install step — download it, mark it executable once, double-click
# (or run it) from then on.
#
# Requires real internet access to GitHub (api.github.com, for the base
# Python-AppImage runtime) and PyPI, which is why this script is meant to be
# run on a normal machine or in CI, not inside a network-restricted sandbox.
set -euo pipefail
cd "$(dirname "$0")"
APPIMAGE_DIR="$(pwd)"
REPO_DIR="$(cd ../.. && pwd)"

echo "== ScreenWatch AppImage builder =="

if ! python3 -c "import python_appimage" >/dev/null 2>&1; then
    echo "Installing python-appimage..."
    pip3 install --quiet --upgrade python-appimage
fi

# python-appimage's `build app` command looks for *.appdata.xml (the legacy
# AppStream filename); our canonical metadata is the modern *.metainfo.xml
# shared with the Flatpak packaging, so mirror it here at build time rather
# than hand-maintaining two copies.
cp "$REPO_DIR/packaging/io.github.mozaher.ScreenWatch.metainfo.xml" \
   "$APPIMAGE_DIR/ScreenWatch.appdata.xml"

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
