#!/usr/bin/env bash
# Builds two separate source .zip files -- one for Linux, one for Windows --
# so the two install paths are genuinely separate downloads, not the
# combined source zip both installer scripts used to ship together in.
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT_DIR="packaging/source-packages"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/linux/VClick" "$STAGE/windows/VClick"
# git archive already respects .gitattributes export-ignore, so packaging/
# and .github/ come out excluded automatically -- no extra logic needed.
git archive HEAD | tar -x -C "$STAGE/linux/VClick"
git archive HEAD | tar -x -C "$STAGE/windows/VClick"

# git archive HEAD only reflects the last commit, never this run's on-disk
# build stamp (written by packaging/stamp_build_info.py just before this
# script runs, for the update-notification feature) -- overwrite what
# git archive extracted with the real, stamped file.
cp vclick/build_info.py "$STAGE/linux/VClick/vclick/build_info.py"
cp vclick/build_info.py "$STAGE/windows/VClick/vclick/build_info.py"

# Each platform only gets its own installer/runner/launcher files.
rm -f "$STAGE/linux/VClick/install.bat" "$STAGE/linux/VClick/run.bat"
rm -f "$STAGE/windows/VClick/install.sh" "$STAGE/windows/VClick/run.sh"
rm -rf "$STAGE/windows/VClick/assets"   # assets/vclick.desktop is Linux-only

mkdir -p "$OUT_DIR"
( cd "$STAGE/linux" && zip -rq "$OLDPWD/$OUT_DIR/VClick-linux-source.zip" VClick )
( cd "$STAGE/windows" && zip -rq "$OLDPWD/$OUT_DIR/VClick-windows-source.zip" VClick )

echo "Wrote:"
echo "  $OUT_DIR/VClick-linux-source.zip"
echo "  $OUT_DIR/VClick-windows-source.zip"
