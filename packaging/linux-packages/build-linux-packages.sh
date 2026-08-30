#!/usr/bin/env bash
# Builds native VClick-x86_64.deb and VClick-x86_64.rpm packages: a
# PyInstaller onedir bundle (Python, Tkinter, and every dependency, the
# same approach packaging/windows-exe used before it was replaced) staged
# under /opt/vclick and wrapped into both package formats with fpm --
# one bundle, two package formats, no separate Debian/Fedora build host
# needed. Must be run on Linux (PyInstaller cannot cross-compile from
# another OS).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
HERE="packaging/linux-packages"

echo "== VClick .deb/.rpm builder =="

VERSION="$(python3 -c 'import vclick; print(vclick.__version__)')"

# A regular (non-editable) install: an editable install's import-hook
# machinery is invisible to PyInstaller's static analyzer, which then
# fails to bundle any vclick submodule at all (confirmed for real, same
# as packaging/windows-exe hit).
python3 -m pip install --upgrade pip
pip install .
pip install pyinstaller

rm -rf "$HERE/build" "$HERE/dist" "$HERE/stage" "$HERE"/*.spec

# --collect-data customtkinter: CustomTkinter ships its theme JSON files
# and font files (assets/themes/*.json, assets/fonts/*) as package data,
# which PyInstaller's static import analysis doesn't pick up on its own.
# --hidden-import for pynput's X11 backend: belt-and-suspenders alongside
# pyinstaller-hooks-contrib's own pynput hook, matching how the old
# Windows build pinned pynput's win32 backend explicitly.
pyinstaller --onedir --windowed --noconfirm --name vclick \
  --add-data "$PWD/vclick/assets:vclick/assets" \
  --collect-data customtkinter \
  --hidden-import mss.linux \
  --hidden-import pynput.mouse._xorg \
  --hidden-import pynput.keyboard._xorg \
  --distpath "$PWD/$HERE/dist" \
  --workpath "$PWD/$HERE/build" \
  --specpath "$PWD/$HERE" \
  "$PWD/$HERE/entrypoint.py"

STAGE="$HERE/stage"
rm -rf "$STAGE"
mkdir -p "$STAGE/opt/vclick" "$STAGE/usr/bin" \
  "$STAGE/usr/share/applications" "$STAGE/usr/share/icons/hicolor/256x256/apps"

cp -r "$HERE/dist/vclick/." "$STAGE/opt/vclick/"
ln -s /opt/vclick/vclick "$STAGE/usr/bin/vclick"
cp "$HERE/vclick.desktop" "$STAGE/usr/share/applications/vclick.desktop"
cp vclick/assets/icon.png "$STAGE/usr/share/icons/hicolor/256x256/apps/vclick.png"

COMMON_ARGS=(
  -s dir -C "$STAGE"
  -n vclick -v "$VERSION"
  --license MIT
  --url "https://github.com/marwan-softdev/VClick"
  --description "Watch a screen area and auto-click a location the moment it changes."
  --maintainer "VClick"
  --category utils
)

fpm "${COMMON_ARGS[@]}" -t deb -a amd64 -p "$HERE/VClick-x86_64.deb" \
  --deb-no-default-config-files .

# rpmbuild's default post-processing (%__os_install_post) tries to
# strip/build-id-link every ELF file it finds, which -- run against a
# PyInstaller bundle full of vendored third-party .so files rather than
# something rpmbuild itself compiled -- produces nothing but ~500 useless
# /usr/lib/.build-id/* symlinks (confirmed for real). Disable both of
# those steps; the binaries are used as-is.
fpm "${COMMON_ARGS[@]}" -t rpm -a x86_64 -p "$HERE/VClick-x86_64.rpm" \
  --rpm-rpmbuild-define "__os_install_post %{nil}" \
  --rpm-rpmbuild-define "_build_id_links none" \
  .

echo
echo "Done:"
echo "  $HERE/VClick-x86_64.deb"
echo "  $HERE/VClick-x86_64.rpm"
