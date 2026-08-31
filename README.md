<a name="top"></a>
# VisualClick

**Watch a region of your screen and auto-click a location the moment it changes.**

VisualClick continuously monitors a screen area you pick. The instant that area
changes visually — a button lights up, a number updates, a progress bar
finishes — it clicks a location you pick. Both are chosen visually, live on
your real desktop, through a clean GUI. Runs for hours on minimal CPU/memory,
natively on both Linux and Windows.

## Contents

- [Highlights](#highlights)
- [Requirements](#requirements)
- [Install](#install)
- [How to use it](#how-to-use-it)
- [Settings explained](#settings-explained)
- [Platform notes](#platform-notes)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [License](#license)

---

## Highlights
- **Very low resource use** — under 1% CPU while watching (measured on
  an 800×600 region at 5 checks/sec), so it can run in the background for
  hours without crashing.
- **Two detection modes** — react to *any* change, or only when the region
  changes from how it looked when you selected the area.
- **Sensitivity & noise controls** — tune how big a change has to be to
  count, and filter out flicker or compression noise.
- **Flexible clicking** — left, right, or middle button, single or double
  click, with an optional delay and a cooldown between clicks.
- **"Why did it click?"** — every click is logged with a picture of exactly
  what changed, so you can verify or debug what triggered it.
- **Remembers your settings** between runs.
- **Works on Linux and Windows**, including Wayland (see [platform
  notes](#platform-notes) for the details).

## Requirements

Python 3.8+, plus `mss`, `numpy`, `pynput`, `Pillow`, and `customtkinter` —
installed automatically by the steps below.

- **Linux** (X11 recommended, Wayland works via a helper — see [platform
  notes](#platform-notes)): also needs system Tkinter (`python3-tk` on
  Debian/Ubuntu — a separate package on some distros).
- **Windows** 10/11: install Python from
  [python.org](https://www.python.org/downloads/windows/) with **"Add
  python.exe to PATH"** ticked — that installer already bundles Tkinter.
- **macOS**: not currently supported.

## Install

### Linux

```bash
git clone https://github.com/marwan-softdev/VClick.git vclick && cd vclick
./install.sh      # installs python3-tk + VisualClick, adds an app-menu icon
```

No terminal needed after this one-time install — launch it from your
application menu from then on.

<details>
<summary>Other Linux install options: AppImage, .deb/.rpm, manual</summary>

- **AppImage** (no sudo, no install step): download
  `VisualClick-*.AppImage` from the
  [`appimage-latest` release](../../releases/tag/appimage-latest),
  mark it executable, and double-click it.
- **Native package**: `VClick-x86_64.deb` or `VClick-x86_64.rpm` from the
  [`linux-packages-latest` release](../../releases/tag/linux-packages-latest) —
  both self-contained, `sudo dpkg -i ...` / `sudo rpm -i ...`.
- **Manual, no launcher icon**:
  ```bash
  sudo apt install python3-tk    # Fedora: python3-tkinter, Arch: tk
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  python -m vclick
  ```
</details>

### Windows

**Option 1: Double-click (easiest)**
1. Download the source zip from the [latest release](../../releases/tag/source-packages-latest) and extract it.
2. Navigate to the extracted folder and **double-click `install.bat`** — that's it!
3. The installer runs and creates a Start Menu shortcut (and a Desktop icon) with VisualClick's own icon.
4. From then on, search **"VisualClick"** in the Start Menu or double-click the desktop icon — it opens with **no console window**.

**Option 2: From command terminal** (if you prefer)
```bat
git clone https://github.com/marwan-softdev/VClick.git vclick
cd vclick
install.bat
```

Either way, `install.bat` creates a Start Menu shortcut (and a Desktop icon) with VisualClick's own icon, so you can launch it easily from your start menu or desktop — no terminal needed after the one-time install.

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
./run.sh --check      # Linux
run.bat --check        REM Windows
```

Example, on a normal Linux X11 desktop:

```
VClick 0.1.0
platform     : Linux 6.8.0
session type : x11
DISPLAY      : :0
WAYLAND      : (unset)
tkinter      : available
mss (capture): available
customtkinter: available (theme assets found)
click backend: pynput
sound backend: paplay
config path  : ~/.config/vclick/config.json
```

## How to use it

1. **Select the watch region** — click *Select…* next to "Watch region", then
   drag a rectangle over the area to monitor.
2. **Select the click point** — click *Select…* next to "Click point", then
   click where you want it to click.
3. **Tune detection** (optional) — Sensitivity, Check rate, Noise filter.
   Defaults work well for most cases.
4. **Press ▶ Start.** It watches; when the region changes, it clicks and logs why.
5. **Press ■ Stop** (or your hotkey) when done.

### Seeing why a click happened

Every triggered click is a row in the **Why / Log** tab. Click any row to see
a picture of what changed — unchanged pixels in greyscale, changed pixels in
red. From there: view it larger, save it as a PNG, or clear the log. Turn it
off entirely with **Explain detections** for the absolute minimum overhead.

## Settings explained

| Setting | What it does |
|---|---|
| **Sensitivity** (1–100) | Higher reacts to smaller visual changes. 50 is a good start. |
| **Check rate (fps)** | How often the region is sampled. Lower = less CPU. |
| **Noise filter** (0–255) | Ignores per-pixel colour changes below this — kills flicker/compression noise. |
| **Compare against** | *Previous frame*: any change. *Start frame*: deviation from how it looked at Start. |
| **Button / Type** | Which mouse button; single or double click. |
| **Cooldown (s)** | Minimum time between clicks; also lets the click's own effect settle before re-checking. |
| **Delay (s)** | Wait this long after detecting a change before clicking. |
| **Max clicks** | Auto-stop after N clicks (0 = unlimited). |
| **Beep on each click** | Plays a notification sound, with an X11-bell fallback on Linux. |
| **Explain detections** | Capture an image of changed pixels per click. Turn off for minimum overhead. |
| **Log history** | How many past detections stay browsable (bounded, so long runs don't grow memory). |
| **Hotkeys** | Enable/disable global hotkeys and record custom combinations. |

Settings save on exit to `~/.config/vclick/config.json` (Linux) or
`%APPDATA%\VClick\config.json` (Windows).

## Platform notes

| | Windows | Linux X11 | Linux Wayland |
|---|---|---|---|
| Screen capture | ✅ `mss` | ✅ `mss` | ⚠️ restricted by the compositor |
| Clicking | ✅ `pynput` | ✅ `pynput` | ✅ via `ydotool` (needs `ydotoold` running) |
| Global hotkeys | ✅ `pynput` | ✅ `pynput` | ❌ usually blocked — use the on-screen button |
| Launcher icon | ✅ Start Menu + Desktop | ✅ app menu | ✅ app menu |

- **Linux**: for the smoothest experience use an X11 session (VisualClick runs
  fine under XWayland too). On native Wayland, install `ydotool` for clicking.
- **Windows**: a global hotkey can't reach a window running as Administrator
  unless VisualClick is *also* elevated — if a hotkey stops working, check that.

## Troubleshooting

- **"No click backend available."** Windows: reinstall. Linux: install
  `pynput` (X11) or `ydotool` (Wayland). Run `--check` to confirm.
- **Tkinter error / blank window.** Linux: install `python3-tk`. Windows:
  reinstall Python from python.org (a Microsoft Store Python install
  sometimes lacks Tkinter).
- **Global hotkeys don't work.** Probably Wayland (Linux) — use the on-screen
  button. On Windows, check Administrator elevation (see [Platform
  notes](#platform-notes)).
- **No launcher icon appeared.** Re-run `install.sh`/`install.bat` (safe to
  repeat); on Linux, log out and back in.
- **Clicks too often / not enough.** Adjust **Sensitivity** and **Noise
  filter**, and raise the **Cooldown**.

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest -q
```

The core (config, capture, detector, monitor) has no import-time GUI/input
dependencies, so it tests cleanly headless. Windows-only code paths are
covered by tests that simulate `sys.platform == "win32"`.

## License

MIT — see [LICENSE](LICENSE).

<p align="right"><a href="#top">Back to top ↑</a></p>
