# ScreenWatch packaging

This directory holds everything needed to distribute ScreenWatch as a
single-click install, in two forms:

- **AppImage** (`appimage/`) — one portable file, no install step at all.
- **Flatpak** (`flatpak/`) — installs like any Software Manager app, and is
  what a Flathub submission is built from.

Both share `io.github.mozaher.ScreenWatch.metainfo.xml` and use the app ID
`io.github.mozaher.ScreenWatch` (matching the GitHub account `mozaher`).

---

## Why not a `.tar.gz` + `install.sh` + `.desktop` file?

That's a reasonable instinct if you're picturing a Windows-style
self-extracting installer, but **it doesn't work that way on Linux**:
double-clicking a `.tar.gz` in every mainstream file manager (GNOME Files,
Dolphin, Thunar, Nemo...) opens an **archive viewer**, not an installer —
there's no OS-level "double-click a tar.gz to run its installer" mechanism on
any Linux desktop. The actual steps would be: double-click → archive manager
opens → click Extract → open the extracted folder → find `install.sh` →
double-click it, which most file managers either open in a **text editor** or
meet with a "Run / Display / Cancel" prompt (not run automatically) unless a
non-default preference is set first. That's *more* steps than what ScreenWatch
already has (`install.sh` once from a terminal), and it isn't consistent
across desktop environments.

**AppImage is the real equivalent of a portable Windows .exe:** download one
file, right-click → Properties → Permissions → tick "Allow executing as
program" (a checkbox, no typing) — or many file managers now prompt "Trust
and Launch" directly — then double-click it from then on. No install, no
root, no terminal, works on (almost) any distro, can even run from a USB
stick. That's what `appimage/build-appimage.sh` produces.

**Flatpak** (your second request) goes a step further: once on Flathub, there
is no download step at all — open Software Manager, search "ScreenWatch",
click Install. This fully subsumes the tar.gz idea for anyone on a
Flatpak-enabled distro (essentially all of them today).

**Recommendation:** ship the AppImage now (works immediately, no review
process) and pursue the Flathub submission in parallel (better long-term
experience, but requires human review — see below).

---

## Honest verification status

This was built in a network-restricted sandbox. Here's exactly what was and
wasn't possible to verify directly, so nothing here is oversold:

**Verified for real, in that sandbox:**
- Every Python dependency wheel's URL and sha256 (via PyPI's JSON API,
  cross-checked against an independently computed local hash).
- The Tcl 8.6.14 and Tk 8.6.14 source archives' URLs and sha256 (downloaded
  from sourceforge.net and hashed locally).
- `packaging/io.github.mozaher.ScreenWatch.metainfo.xml` — validated with
  `appstreamcli validate` (Flathub's own class of tooling).
- `packaging/*.desktop` and `packaging/appimage/ScreenWatch.desktop` —
  validated with `desktop-file-validate`.
- The Flatpak manifest's structure/schema — parsed successfully by the real
  `flatpak-builder --show-manifest`, and every local source path it
  references was confirmed to exist.
- `python-appimage`'s expected input layout (`requirements.txt`, `*.desktop`,
  icon, `entrypoint.sh`, `{{ python-executable }}` templating) — read
  directly from its installed source, not guessed.
- The actual app: launched under a virtual X server, screenshotted (that
  screenshot is in `screenshots/main.png` and is what the metainfo references
  — not a placeholder).

**Not verifiable from that sandbox** (its egress policy explicitly denies
`flathub.org`, `dl.flathub.org`, and `github.com`'s release/API endpoints —
confirmed, not assumed, and not worked around per that policy):
- A full `flatpak-builder` build. The **one genuine unknown** it would
  resolve: whether `org.freedesktop.Sdk`'s bundled Python already has the
  `_tkinter` extension compiled in (this manifest only supplies the Tcl/Tk
  *runtime libraries*; if `_tkinter` was never compiled against them in the
  first place, the fix is building Python from source too, with
  `--with-tcltk-*` flags — a bigger but well-documented change).
- Actually running `python-appimage build app`, which needs to fetch its base
  runtime from `api.github.com`.
- The `.github/workflows/packaging.yml` CI workflow itself, since it needs
  GitHub's own runners.

**How that gap gets closed:** the CI workflow above builds both formats for
real on GitHub's infrastructure the moment this is pushed, and uploads the
results as workflow artifacts — including a directly-installable `.flatpak`
bundle, no Flathub review required to try it. If the Flatpak build fails at
the Python/Tkinter step, that's the one open question above; ask for it to be
fixed and the manifest can be adjusted to build Python from source instead.

---

## Submitting to Flathub — what only you can do

Flathub review is inherently a human process tied to your identity; here's
exactly what's already done versus what needs you:

**Already done:**
- App ID chosen: `io.github.mozaher.ScreenWatch` (derived from your GitHub
  username, since there's no owned domain to reverse — this is the standard
  convention. **This is effectively permanent once published — say now if
  you'd rather use something else.**)
- Manifest, AppStream metadata, desktop file, and icon all written and
  validated as far as this sandbox allows (see above).
- A real screenshot captured and referenced.

**Needs you:**
1. **Confirm the repo will be public.** Flathub's build servers fetch your
   source over plain `git clone` with no authentication — a private repo
   can't be built. (This session's own git access works through a different,
   authenticated path, which is why the manifest itself could be validated
   here even though this point couldn't be.)
2. **Cut a release tag** and update the `branch:` field in
   `flatpak/io.github.mozaher.ScreenWatch.yml` and the `git+...@` ref in
   `appimage/requirements.txt` to point at it instead of a floating branch —
   Flathub reviewers expect a pinned, reproducible source.
3. **Open the submission PR** at github.com/flathub/flathub (see
   [docs.flathub.org/docs/for-app-authors/submission](https://docs.flathub.org/docs/for-app-authors/submission))
   with `packaging/flatpak/io.github.mozaher.ScreenWatch.yml` as the
   manifest. This requires your own GitHub account and needs to be you
   because reviewers will ask follow-up questions over days—weeks that only
   the submitter can answer authoritatively.
4. **Respond to reviewer feedback.** Common first-round requests: a stable
   release tag (point 2), sometimes tweaks to permissions or metadata wording.

---

## Building locally

```bash
# AppImage (needs real internet access — GitHub + PyPI)
bash packaging/appimage/build-appimage.sh

# Flatpak (needs flatpak, flatpak-builder, and the freedesktop 23.08
# runtime + SDK installed — `flatpak install flathub org.freedesktop.{Platform,Sdk}//23.08`)
flatpak-builder --user --install --force-clean \
    packaging/flatpak/build-dir \
    packaging/flatpak/io.github.mozaher.ScreenWatch.yml
flatpak run io.github.mozaher.ScreenWatch
```
