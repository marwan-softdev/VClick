# VisualClick 👁️🖱️

**Watch a region of your screen and auto-click a location the moment it changes.**

VisualClick continuously monitors a screen area you pick. The instant that area
changes *visually* — a button lights up, a number updates, an image loads, a
progress bar finishes — it clicks a location you pick. Both the watched region
and the click point are chosen visually through a clean, friendly GUI.

It is built to run **for hours** with a tiny CPU and memory footprint, and
runs natively on **both Linux and Windows**.

---

## Highlights

- 🖼️ **Truly live point-and-drag selection** — the screen is **never covered**.
  You drag directly over your real, moving desktop (video keeps playing, UIs keep
  animating), with no compositor required. Press **Esc or right-click** to cancel.
- ⚡ **Low resource use** — the watched region is down-scaled before diffing with
  NumPy. On an 800×600 region this is **~0.32% of one CPU core at 5 fps** and
  under 100 KiB of working memory. Made for 4–5 hour runs.
- 🎚️ **Sensitivity & noise controls** — react to the tiniest flicker or only to
  big changes; a noise filter ignores compression/render jitter.
- 🧠 **Two detection modes** — react to *any* change (vs. the previous frame) or
  to *deviation from a starting state* (vs. the frame captured on Start).
- 🖱️ **Flexible clicking** — left / right / middle, single or double, optional
  delay, and a **cooldown** so it never machine-guns clicks.
- 🔍 **"Why did it click?"** — every click is logged as a row you can click on to
  see a picture of exactly what triggered it: the watched region with the
  responsible pixels highlighted in red. View it larger, or save it as a PNG.
- ⌨️ **Customizable global hotkeys** — record any combination for start/stop and
  quit (defaults `Ctrl+Shift+S` / `Ctrl+Shift+Q`) right in the Hotkeys tab
  (Windows & Linux X11).
- 💾 **Remembers everything** — settings and selections persist between runs.
- 🖥️ **Linux + Windows, with a real launcher icon** — the installer for each
  platform registers VisualClick in your application menu / Start Menu with
  its own icon, so day-to-day you launch it by clicking, never a terminal.
- 🐧 **X11 & Wayland aware on Linux** — best on X11; on Wayland it falls back
  to `ydotool`/`xdotool` for clicking and tells you what it needs.

---

## Requirements

**Linux** (X11 recommended; Wayland supported with a helper — see
[platform notes](#platform-notes)):
- Python 3.8+
- System Tkinter (`python3-tk` on Debian/Ubuntu) — ships with Python but is a
  separate package on many distros.

**Windows** 10 or 11:
- Python 3.8+ from [python.org](https://www.python.org/downloads/windows/),
  with **"Add python.exe to PATH"** ticked during setup. That installer
  already bundles Tkinter — nothing extra to install.

Both platforms: `mss`, `numpy`, `pynput`, `Pillow`, `customtkinter` (installed
automatically by the steps below).

---

## Install

### Linux

```bash
git clone <this-repo> vclick && cd vclick
./install.sh      # installs python3-tk + VisualClick, adds an app-menu icon
```

VisualClick opens automatically once the install finishes. From then on,
open it from your application menu / app list like any other program (search
for it by name). No terminal needed after this one-time install.

#### No sudo / no terminal at all: AppImage

Prefer a single portable file, or don't have root access? Download the
self-contained `VisualClick-*.AppImage` (bundled Python, Tkinter, and
dependencies included) from the
**[`appimage-latest-screen-change-q8eylj` release](../../releases/tag/appimage-latest-screen-change-q8eylj)**. Mark it
executable once (a checkbox in your file manager, no typing) and double-click
it from then on — no install step, no root, nothing to build. (The build
tooling behind that release lives in `packaging/appimage/` in the full
repository on GitHub — it's deliberately left out of the source zip above,
which is for the install.sh/install.bat path.)

#### Native package: .deb / .rpm

Prefer a package your system's package manager tracks? Grab
`VClick-x86_64.deb` (Debian, Ubuntu, and derivatives) or `VClick-x86_64.rpm`
(Fedora, openSUSE, and derivatives) from the
**[`linux-packages-latest-screen-change-q8eylj` release](../../releases/tag/linux-packages-latest-screen-change-q8eylj)**.
Both are self-contained — bundled Python, Tkinter, and every dependency —
so nothing else needs to be installed first; `sudo dpkg -i VClick-x86_64.deb`
or `sudo rpm -i VClick-x86_64.rpm` adds a `vclick` command and an app-menu
launcher. (Build tooling: `packaging/linux-packages/`.)

<details>
<summary>Manual install (no launcher icon, no python3-tk auto-install)</summary>

```bash
sudo apt install python3-tk    # Debian/Ubuntu (Fedora: python3-tkinter, Arch: tk)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m vclick
```
</details>

### Windows

```bat
git clone <this-repo> vclick
cd vclick
install.bat
```

That's it — `install.bat` creates a Start Menu shortcut (and a Desktop icon)
with VisualClick's own icon. Search **"VisualClick"** in the Start Menu, or
double-click the desktop icon — it opens with **no console window**.

<details>
<summary>Manual install (no shortcuts)</summary>

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m vclick
```
</details>

### Check your environment at any time

```bash
./run.sh --check      # Linux — reports platform, tkinter, capture/click/sound backends
run.bat --check        REM Windows
```

---

## How to use it

1. **Select the watch region** — click *Select…* next to “Watch region”, then
   drag a rectangle over the area to monitor.
2. **Select the click point** — click *Select…* next to “Click point”, then click
   where you want VisualClick to click.
3. **Tune detection** (optional) — set Sensitivity, Check rate, and the Noise
   filter. Defaults work well for most cases.
4. **Press ▶ Start.** VisualClick now watches. When the region changes, it clicks
   your point. The status bar shows live activity, click count, and uptime.
5. **Press ■ Stop** (or your start/stop hotkey) when you’re done.

Customize the hotkeys in the **Hotkeys** tab — click *Change…* and press the
combination you want.

### Seeing *why* a click happened

Every triggered click becomes a row in the **Why / Log** tab:

| # | Time | Changed | Image |
|---|---|---|---|
| 3 | 14:22:07 | 4.61% | 🖼 |
| 2 | 14:19:55 | 1.08% | 🖼 |
| 1 | 14:18:30 | 12.44% | 🖼 |

**Click any row** to see a picture of what triggered that specific click. Areas
that did **not** change are rendered in dark greyscale, the pixels that *did*
change are painted bright red, and a cyan box outlines where they are — so the
highlight stays obvious even over already-red or orange content.
From there you can:

* **View larger ⤢** (or double-click the row) to open it magnified in its own window;
* **Save image…** to export it as a PNG;
* drag the divider between the log and the picture to resize either half;
* untick **Follow newest** to stay on an older detection while monitoring continues;
* **Clear** to empty the log.

Turn the whole thing off with the *Explain detections* checkbox if you want the
absolute minimum overhead.

> Tip: While selecting, press **Escape or right-click** to cancel without
> changing anything.

#### How live selection works

Most region pickers freeze a screenshot, or lay a translucent sheet over the
desktop — which needs a compositing window manager and renders as a **solid
black screen** without one. VisualClick does neither:

* a 1×1, effectively invisible window takes a **global pointer grab**, so every
  mouse move and click anywhere on screen is delivered with absolute
  coordinates;
* the selection is drawn as a few **thin border strips** that outline your
  rectangle, plus a live `W × H` readout.

Nothing is ever layered over your desktop, so what you drag over is the real
thing, updating in real time — compositor or not.

### The window at a glance

```
VisualClick — auto-click on change
──────────────────────────────────────────────
Watches a screen area and clicks the instant it changes.

┌ Targets & Detection │ Clicking │ Hotkeys │ Why / Log ┐
│ Targets                                              │
│   Watch region:  640×48 at (1200, 300)   [Select…]   │
│   Click point:   (1420, 690)             [Select…]   │
│ Detection                                            │
│   Sensitivity     ──────●────────  62                │
│   Check rate (fps)──●────────────  5.0               │
│   Noise filter    ────●──────────  25                │
│   Compare against: (•) Previous frame ( ) Start frame│
└──────────────────────────────────────────────────────┘
        ▶  Start
   [▓▓▓▓░░░░░░░░░░░░░]  activity
   ● Watching…   clicks: 3 · uptime: 12m 04s · change: 0.81%
   Active — Ctrl+Shift+S start/stop · Ctrl+Shift+Q quit
```

The **Why / Log** tab keeps a browsable history: click any logged detection to
see the picture of what triggered it.

---

## Settings explained

| Setting | What it does |
|---|---|
| **Sensitivity** (1–100) | Higher reacts to smaller visual changes. 50 is a good start. |
| **Check rate (fps)** | How often the region is sampled. Lower = less CPU. 3–5 fps is plenty for most UIs. |
| **Noise filter** (0–255) | A pixel counts as changed once its strongest colour channel moves by more than this — kills flicker/compression noise while still catching hue changes (e.g. a button swapping colour) that a brightness-only check would miss. |
| **Compare against** | *Previous frame*: fires on any change/motion. *Start frame*: fires when the area deviates from how it looked at Start. |
| **Button / Type** | Which mouse button; single or double click. |
| **Cooldown (s)** | Minimum time between clicks; also the settle time so the click’s own visual effect doesn’t re-trigger detection. |
| **Delay (s)** | Wait this long after detecting a change before clicking. |
| **Max clicks** | Auto-stop after N clicks (0 = unlimited). |
| **Beep on each click** | Plays a real notification sound (`canberra-gtk-play`, `paplay`, `pw-play`, `ffplay` or `aplay`), falling back to the X11 bell. Install one of those if you hear nothing. |
| **Explain detections** | Capture an image of which pixels changed, viewable per-click in the “Why / Log” tab. Turn off for the absolute minimum overhead. |
| **Log history** | How many past detections (and their images) stay browsable. Bounded so multi-hour runs can't grow memory — typical screen content is under 1 KiB per image. |
| **Hotkeys** | Enable/disable global hotkeys and record custom combinations for start/stop and quit. |

Settings are saved on exit (or via **File → Save settings**) to
`~/.config/vclick/config.json` on Linux, or `%APPDATA%\VClick\config.json`
on Windows.

---

## Performance & long runs

VisualClick is designed to sit in the background for hours:

- Only the selected region is captured (via `mss`), then **down-sampled to a
  ~120 px colour array** before any comparison — the diff cost is independent
  of your monitor size.
- The loop is **time-paced**, never a busy-wait, and sleeps on the stop-event so
  stopping is instant.
- Measured cost of capture-convert + detect on an 800×600 region: **~0.63 ms per
  frame** → about **0.32% of one core at 5 fps**. Working memory for detection is
  a couple of small buffers (under 100 KiB).

To minimise CPU further: lower the **Check rate**, keep the watched region small,
and raise the **Noise filter** so trivial changes are skipped.

---

## Platform notes

| | Windows | Linux X11 | Linux Wayland |
|---|---|---|---|
| Screen capture | ✅ `mss` | ✅ `mss` | ⚠️ region capture is restricted by the compositor |
| Clicking | ✅ `pynput` (native `SendInput`) | ✅ `pynput` | ✅ via `ydotool` (needs `ydotoold` running) |
| Global hotkeys | ✅ `pynput` | ✅ `pynput` | ❌ usually blocked — use the on-screen button |
| Sound feedback | ✅ `winsound` (built in) | ✅ via a CLI player if installed | ✅ via a CLI player if installed |
| Launcher icon | ✅ Start Menu + Desktop (`install.bat`) | ✅ app menu (`install.sh`) | ✅ app menu (`install.sh`) |

The Hotkeys tab confirms receipt (“✔ start/stop hotkey received at …”) whenever a
combination reaches the app, and its **key tester** shows the last combination the
listener saw — so you can tell “not detected at all” from “detected but not
matching”.

Matching is done by tracking modifier state and normalising the trigger key,
rather than by comparing characters. That matters because Ctrl-held combinations
often deliver a *control character* instead of the letter (`Ctrl+A` arrives as
`\x01`, `Ctrl+Z` as `\x1a`, on both Windows and X11) — the reason naive
character-based matching lets plain `A` work while `Ctrl+Shift+A` silently does
nothing.

**On Linux**, for the smoothest experience run an **X11 session** (pick
“Xorg”/“X11” at your login screen). VisualClick runs fine under XWayland. On
native Wayland, install `ydotool` for clicking; `./run.sh --check` will show
which click backend is active.

**On Windows**, a global hotkey can't reach a window running as Administrator
unless VisualClick is *also* running as Administrator (a Windows security
rule, not a bug) — if a hotkey mysteriously stops working, check whether the
target application is elevated.

---

## Troubleshooting

- **“No click backend available.”** On Windows, reinstall — `pynput` should
  have come with `install.bat`/`pip install -r requirements.txt`. On Linux,
  install `pynput` (X11) or `ydotool`/`xdotool` (Wayland). Run `./run.sh
  --check` (or `run.bat --check`) to confirm.
- **Tkinter error / blank window.** Linux: install `python3-tk` (or your
  distro's equivalent). Windows: reinstall Python from python.org, which
  bundles Tkinter — a Microsoft Store Python install sometimes doesn't.
- **Global hotkeys don't work.** On Linux you're probably on Wayland — use the
  Start/Stop button; the hint under the button will say so. On Windows, check
  whether the app you're clicking into is running as Administrator (see
  [Platform notes](#platform-notes)).
- **No launcher icon appeared.** Re-run `./install.sh` / `install.bat` — it's
  safe to run again. On Linux, log out and back in if your desktop caches its
  application menu.
- **It clicks too often / not enough.** Adjust **Sensitivity** and the **Noise
  filter**, and raise the **Cooldown**.

---

## Project layout

```
vclick/
  __init__.py        package metadata
  __main__.py        CLI entry point (python -m vclick, --check, --version)
  config.py          settings dataclass + JSON persistence (no GUI deps)
  capture.py         mss capture + fast colour down-sampling
  detector.py        NumPy change detection
  clicker.py         pynput / ydotool / xdotool click backends
  monitor.py         the capture→detect→click worker thread
  hotkeys.py         global hotkeys, layout/modifier-robust key matching
  sound.py           click feedback: winsound (Windows) / CLI players (Linux)
  paths.py           locates the bundled icon regardless of how it was installed
  history.py         bounded per-detection history behind the Why/Log tab
  region_selector.py fullscreen overlays for picking region & point
  gui.py             the CustomTkinter window
  assets/            app icon (icon.png, icon.ico), packaged with the app
assets/
  vclick.desktop  Linux launcher template, filled in by install.sh
tests/               headless unit + end-to-end tests
```

---

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest -q          # 94 tests, all run headless (no display needed)
```

The core (config, capture, detector, monitor) has **no import-time GUI or input
dependencies**, so it imports and tests cleanly on headless CI. The monitor loop
is covered end-to-end with a faked screen and mouse. Windows-only code paths
(the `%APPDATA%` config location, the `winsound` audio backend) are covered by
tests that simulate `sys.platform == "win32"`, since CI here runs on Linux —
see [Verifying the Windows support](#verifying-the-windows-support) below.

---

## Verifying the Windows support

This project was developed and tested on Linux; there is no Windows machine in
that loop. What's actually been verified, and how:

- **Runtime logic that differs by platform** — the `%APPDATA%` config path and
  the `winsound` sound backend — is unit-tested by simulating
  `sys.platform == "win32"` (see `tests/test_cross_platform.py`). This checks
  the *logic* is correct; it can't execute real `winsound` calls or produce
  real Windows path separators (those are properties of the actual OS, not of
  `sys.platform`, so the tests build their expectations the same portable way
  rather than hard-coding one platform's separator).
- **pynput's Windows backend** (mouse `SendInput`, keyboard hooks) is a
  well-established, widely used library; the *matching logic* built on top of
  it (`hotkeys.py`) is exercised with unit tests using synthetic key events,
  including the exact Ctrl-produces-a-control-character case that Windows and
  X11 share.
- **`install.bat`/`run.bat`** follow standard, documented patterns (`pip`
  editable installs, `gui-scripts` entry points, a `WScript.Shell` COM call
  for shortcuts) but have not been executed on a real Windows machine.
- **Everything else — capture, detection, the GUI, the click-log/preview
  system, the Linux installer end-to-end** — has been run and verified for
  real, including launching the actual installed entry point under a virtual
  X server exactly as a desktop-icon click would, and a live before/after
  comparison proving a real screen change on-screen triggers a real click.

If something on Windows doesn't work as documented, that's the most likely
place to look first — please open an issue with the output of `run.bat
--check`.

---

## License

MIT — see [LICENSE](LICENSE).
