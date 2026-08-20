#! /bin/bash
# Entrypoint substituted into AppDir/AppRun by python-appimage (see
# build-appimage.sh). {{ python-executable }} expands to the bundled
# interpreter's path at AppImage RUN time (it depends on $APPDIR, which the
# AppImage runtime sets when the user launches it), not at build time.
exec "{{ python-executable }}" -m screenwatch "$@"
