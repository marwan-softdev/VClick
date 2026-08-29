#!/usr/bin/env bash
# Builds a VClick AppImage: a single, portable executable file that
# needs no install step — download it, mark it executable once, double-click
# (or run it) from then on. No root, no system Python packages required.
#
# Requires real internet access to GitHub (api.github.com + release assets,
# for the base Python-AppImage runtime) and PyPI, for the Python deps.
set -euo pipefail
cd "$(dirname "$0")"
APPIMAGE_DIR="$(pwd)"

echo "== VClick AppImage builder =="

# The icon lives once, at vclick/assets/icon.png -- python-appimage requires
# an icon file in this directory matching the .desktop file's Icon= name, so
# copy it in at build time rather than keeping a second copy checked in.
cp "$APPIMAGE_DIR/../../vclick/assets/icon.png" "$APPIMAGE_DIR/VisualClick.png"

if ! python3 -c "import python_appimage" >/dev/null 2>&1; then
    echo "Installing python-appimage..."
    pip3 install --quiet --upgrade python-appimage
fi

# requirements.txt normally installs VClick from a tarball of the
# branch tip on GitHub -- but that's a *server-side* snapshot fetched fresh
# over the network, which would silently ship whatever commit is on GitHub
# right now instead of this run's actual checkout (and would always miss
# this run's stamped vclick/build_info.py, since that stamp only ever
# exists on disk here -- see packaging/stamp_build_info.py). Build a local
# sdist of the current checkout instead and swap it in for that remote URL
# for just this run, so the AppImage always matches what was actually
# checked out, stamp included.
python3 -m pip install --quiet build setuptools wheel
SDIST_DIR="$(mktemp -d)"
cleanup() {
    rm -rf "$SDIST_DIR"
    if [ -f requirements.txt.orig ]; then
        mv requirements.txt.orig requirements.txt
    fi
}
trap cleanup EXIT
# --no-isolation: build straight in this environment instead of creating a
# throwaway venv for the build backend -- faster, and sidesteps environments
# where that venv can't bootstrap pip into itself (no `ensurepip` module).
( cd "$APPIMAGE_DIR/../.." && python3 -m build --sdist --no-isolation --outdir "$SDIST_DIR" --quiet )
LOCAL_SDIST="$(ls "$SDIST_DIR"/vclick-*.tar.gz)"
grep -v '^https://github.com/marwan-softdev/VClick/archive/' requirements.txt > requirements.local.txt
echo "$LOCAL_SDIST" >> requirements.local.txt
mv requirements.txt requirements.txt.orig
mv requirements.local.txt requirements.txt

echo "Building AppImage (this downloads a base Python runtime + installs deps)..."
python3 -m python_appimage build app \
    --python-version 3.11 \
    "$APPIMAGE_DIR"

echo
echo "Done. The AppImage was written to:"
ls -1 "$APPIMAGE_DIR"/VisualClick-*.AppImage 2>/dev/null || echo "  (check the output above for the exact filename/location)"
echo
echo "To use it: chmod +x the file (or tick 'Allow executing as program' in"
echo "your file manager's Properties dialog), then double-click it. No"
echo "install step, no root, and it can be moved/copied anywhere."
