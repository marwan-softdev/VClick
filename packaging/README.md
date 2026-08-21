# ScreenWatch AppImage

A single portable executable: mark it executable once (a file-manager
checkbox, no typing), double-click from then on. No install step, no root,
no terminal — the real equivalent of a portable Windows `.exe`, and useful
in particular if you don't have `sudo` access for `install.sh`'s system
package steps (Tkinter, `python3-venv`).

## Getting a build

**For end users: download the single `.AppImage` file, don't build it.**
Every push to this branch that touches `screenwatch/`, `pyproject.toml`, or
`packaging/appimage/` triggers the `Build AppImage` GitHub Actions workflow,
which (after a real build and a smoke test) publishes the result to the
[**`appimage-latest` release**](../../releases/tag/appimage-latest) — a
stable, direct-download link to just that one file, deliberately kept
separate from the branch's *source* zip (which is for the `install.sh`
terminal-install path and still contains this build tooling). That release
URL doesn't change between builds; downloading it never requires a GitHub
login, unlike a workflow-run artifact.

**Building it yourself** (for a different CPU architecture, or to test a
change to this packaging) needs a machine with normal internet access to
GitHub and PyPI (this is what the CI workflow does):

```bash
bash packaging/appimage/build-appimage.sh
```

This installs `python-appimage`, downloads a base Python 3.11 AppImage
runtime, bundles ScreenWatch and its dependencies into it, and writes
`ScreenWatch-<version>-x86_64.AppImage` into this directory.

## How it's built

- `build-appimage.sh` drives [`python-appimage`](https://github.com/niess/python-appimage),
  which fetches a prebuilt, relocatable Python 3.11 runtime (from that
  project's GitHub releases) and pip-installs `requirements.txt` into it.
- `requirements.txt` pins ScreenWatch's runtime dependencies plus ScreenWatch
  itself, installed from **a source tarball URL** of this branch rather than
  a `git+...` VCS spec — a `python-appimage` bug in filtering pip's own
  informational git output on this branch's git version otherwise
  misclassifies a harmless line as a fatal error and aborts the build (see
  the comment in `requirements.txt`). Update that URL to a release tag's
  archive once one is cut.
- `ScreenWatch.desktop` / `ScreenWatch.png` become the app's menu entry and
  icon inside the AppImage.
- `entrypoint.sh` becomes the AppImage's `AppRun`: it just execs
  `python -m screenwatch`.

## Verification status

Building this end-to-end from inside this session isn't possible: the base
runtime lookup calls `api.github.com/repos/niess/python-appimage/releases`,
a *different* repository than the one this session has GitHub access
scoped to, and that call is denied for that reason (not a general network
block — confirmed directly from the proxy's own error response). The
`.github/workflows/appimage.yml` CI workflow closes that gap: it runs on
GitHub's own hosted runners, which have no such scoping restriction, and
produces a real build on every relevant push.

What *was* verified directly in this session: `python-appimage`'s expected
input layout (`requirements.txt`, `*.desktop`, icon, `entrypoint.sh`, the
`{{ python-executable }}` templating) was read from the installed tool's own
source, not guessed, and the build was run far enough to confirm it fails
*only* at the network call above (everything before that — argument parsing,
requirements-file parsing — executed normally).
