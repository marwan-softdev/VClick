# ScreenWatch 👁️🖱️

**Watch a region of your screen and auto-click a location the moment it changes.**

ScreenWatch continuously monitors a screen area you pick. The instant that area
changes *visually* — a button lights up, a number updates, an image loads, a
progress bar finishes — it clicks a location you pick. Both the watched region
and the click point are chosen visually through a clean, friendly GUI.

It is built to run **for hours** with a tiny CPU and memory footprint.

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
  quit (defaults `Ctrl+Shift+S` / `Ctrl+Shift+Q`) right in the Hotkeys tab (X11).
- 💾 **Remembers everything** — settings and selections persist between runs.
- 🐧 **X11 & Wayland aware** — best on X11; on Wayland it falls back to
  `ydotool`/`xdotool` for clicking and tells you what it needs.

---

## Requirements

- Linux with a graphical desktop (X11 recommended; Wayland supported with a
  helper — see [Wayland notes](#wayland-vs-x11)).
- Python 3.8+
- System Tkinter (`python3-tk` on Debian/Ubuntu) — ships with Python but is a
  separate package on many distros.
- Python packages: `mss`, `numpy`, `pynput`, `Pillow` (installed automatically).

---

## Install

### Quick (recommended)

```bash
git clone <this-repo> screenwatch && cd screenwatch
./install.sh      # installs python3-tk + a local .venv with the deps
./run.sh          # launch the app
```

### Manual

```bash
# Debian/Ubuntu:  sudo apt install python3-tk
# Fedora:         sudo dnf install python3-tkinter
# Arch:           sudo pacman -S tk

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m screenwatch
```

Check your environment at any time:

```bash
./run.sh --check      # reports session type, tkinter, capture & click backend
```

---

## How to use it

1. **Select the watch region** — click *Select…* next to “Watch region”, then
   drag a rectangle over the area to monitor.
2. **Select the click point** — click *Select…* next to “Click point”, then click
   where you want ScreenWatch to click.
3. **Tune detection** (optional) — set Sensitivity, Check rate, and the Noise
   filter. Defaults work well for most cases.
4. **Press ▶ Start.** ScreenWatch now watches. When the region changes, it clicks
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
black screen** without one. ScreenWatch does neither:

* a 1×1, effectively invisible window takes a **global pointer grab**, so every
  mouse move and click anywhere on screen is delivered with absolute
  coordinates;
* the selection is drawn as a few **thin border strips** that outline your
  rectangle, plus a live `W × H` readout.

Nothing is ever layered over your desktop, so what you drag over is the real
thing, updating in real time — compositor or not.

### The window at a glance

```
ScreenWatch — auto-click on change
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

Settings are saved to `~/.config/screenwatch/config.json` on exit (or via
**File → Save settings**).

---

## Performance & long runs

ScreenWatch is designed to sit in the background for hours:

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

## Wayland vs X11

| | X11 | Wayland |
|---|---|---|
| Screen capture | ✅ `mss` | ⚠️ region capture is restricted by the compositor |
| Clicking | ✅ `pynput` | ✅ via `ydotool` (needs `ydotoold` running) |
| Global hotkeys | ✅ `pynput` | ❌ usually blocked — use the on-screen button |

The Hotkeys tab confirms receipt (“✔ start/stop hotkey received at …”) whenever a
combination reaches the app, and its **key tester** shows the last combination the
listener saw — so you can tell “not detected at all” from “detected but not
matching”.

Matching is done by tracking modifier state and normalising the trigger key,
rather than by comparing characters. That matters because many X setups deliver
a *control character* when Ctrl is held (`Ctrl+A` arrives as `\x01`, `Ctrl+Z` as
`\x1a`), which never equals `a`/`z` — the reason character-based matching lets
plain `A` work while `Ctrl+Shift+A` silently does nothing.

**Recommendation:** for the smoothest experience, run in an **X11 session**
(pick “Xorg”/“X11” at your login screen). ScreenWatch runs fine under XWayland.
On native Wayland, install `ydotool` for clicking; `./run.sh --check` will show
which click backend is active.

---

## Troubleshooting

- **“No click backend available.”** Install `pynput` (X11) or `ydotool`
  (Wayland) / `xdotool` (X11). Run `./run.sh --check` to confirm.
- **Tkinter error / blank window.** Install `python3-tk` (or your distro’s
  equivalent).
- **Global hotkeys don’t work.** You’re probably on Wayland — use the Start/Stop
  button; the hint under the button will say so.
- **It clicks too often / not enough.** Adjust **Sensitivity** and the **Noise
  filter**, and raise the **Cooldown**.

---

## Project layout

```
screenwatch/
  __init__.py        package metadata
  __main__.py        CLI entry point (python -m screenwatch, --check, --version)
  config.py          settings dataclass + JSON persistence (no GUI deps)
  capture.py         mss capture + fast grayscale down-sampling
  detector.py        NumPy change detection
  clicker.py         pynput / ydotool / xdotool click backends
  monitor.py         the capture→detect→click worker thread
  hotkeys.py         optional global hotkeys
  region_selector.py fullscreen overlays for picking region & point
  gui.py             the Tkinter/ttk window
tests/               headless unit + end-to-end tests
```

---

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest -q          # 84 tests, all run headless (no display needed)
```

The core (config, capture, detector, monitor) has **no import-time GUI or input
dependencies**, so it imports and tests cleanly on headless CI. The monitor loop
is covered end-to-end with a faked screen and mouse.

---

## License

MIT — see [LICENSE](LICENSE).
