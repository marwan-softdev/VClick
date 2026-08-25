"""Configuration model and persistence for ScreenWatch.

The whole application state that is worth remembering between runs lives in the
:class:`Config` dataclass.  It is intentionally free of any GUI, capture or
input dependencies so it can be imported and unit-tested anywhere (even on a
headless machine).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Where the config file lives: %APPDATA%\ScreenWatch on Windows (the
# conventional per-user settings location there), the XDG Base Directory
# spec (~/.config or $XDG_CONFIG_HOME) everywhere else.
# ---------------------------------------------------------------------------
def default_config_path() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "ScreenWatch", "config.json")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "screenwatch", "config.json")


@dataclass
class Region:
    """A rectangular screen area in absolute (virtual desktop) coordinates."""

    left: int
    top: int
    width: int
    height: int

    def as_mss_monitor(self) -> Dict[str, int]:
        """Return the dict shape that ``mss`` expects for ``grab``."""
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}

    @property
    def is_valid(self) -> bool:
        return self.width > 0 and self.height > 0

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.width}×{self.height} at ({self.left}, {self.top})"


# Allowed enumerations, kept here so the GUI and validation share one source.
CLICK_BUTTONS = ("left", "right", "middle")
CLICK_TYPES = ("single", "double")
COMPARE_MODES = ("previous", "baseline")
# "system" follows the OS light/dark setting where that's detectable
# (reliably on Windows; on Linux it needs a desktop that exposes it via
# gsettings, and falls back to light when it doesn't).
THEME_MODES = ("system", "light", "dark")


@dataclass
class Config:
    """All persisted user preferences.

    Attributes
    ----------
    region:
        The area of the screen being watched (``None`` until selected).
    click_x, click_y:
        Absolute coordinates that get clicked when a change is detected
        (``None`` until selected).
    fps:
        How many times per second the region is sampled.  Lower = less CPU.
    sensitivity:
        1..100.  Higher values react to smaller visual changes.
    pixel_threshold:
        Per-pixel brightness delta (0..255) that counts a pixel as "changed".
        Filters out camera/render noise.
    cooldown:
        Minimum seconds between two clicks; also the settle time after a click
        so the click's own visual effect does not re-trigger detection.
    click_button / click_type:
        Which mouse button and single vs double click.
    click_delay:
        Optional pause (seconds) between detecting a change and clicking.
    compare_mode:
        ``"previous"`` compares each frame to the one before (reacts to *any*
        change/motion); ``"baseline"`` compares to a fixed reference frame
        captured when monitoring starts (reacts to *deviation* from a state).
    max_clicks:
        Stop automatically after this many clicks (0 = unlimited).
    warmup_frames:
        Frames to ignore at start so the picture can settle.
    play_sound:
        Ring the terminal bell on each click.
    downscale_max:
        Longest edge (px) the region is shrunk to before comparison.  Smaller
        is cheaper; detection stays reliable because we only need relative
        change, not detail.
    """

    region: Optional[Region] = None
    click_x: Optional[int] = None
    click_y: Optional[int] = None

    fps: float = 5.0
    sensitivity: int = 50
    pixel_threshold: int = 25
    cooldown: float = 1.0

    click_button: str = "left"
    click_type: str = "single"
    click_delay: float = 0.0

    compare_mode: str = "previous"
    max_clicks: int = 0
    warmup_frames: int = 2

    play_sound: bool = False
    downscale_max: int = 120

    # Global hotkeys (pynput format, e.g. "<ctrl>+<shift>+s").
    hotkeys_enabled: bool = True
    hotkey_toggle: str = "<ctrl>+<shift>+s"
    hotkey_quit: str = "<ctrl>+<shift>+q"

    # Show a visual explanation (highlighted diff) of each detected change.
    show_detection_preview: bool = True
    # How many past detections (with their images) stay browsable in the log.
    # Bounded so a multi-hour session cannot grow memory without limit.
    log_history: int = 30

    # Window appearance: one of THEME_MODES.
    theme: str = "system"

    # Check for a newer build on launch (also always available on-demand via
    # the "Check for Updates" button in Settings).
    auto_check_updates: bool = True

    # -- validation --------------------------------------------------------
    def clamp(self) -> "Config":
        """Coerce all fields into their valid ranges.  Returns ``self``."""
        self.fps = _clamp(float(self.fps), 0.5, 60.0)
        self.sensitivity = int(_clamp(self.sensitivity, 1, 100))
        self.pixel_threshold = int(_clamp(self.pixel_threshold, 0, 255))
        self.cooldown = _clamp(float(self.cooldown), 0.0, 3600.0)
        self.click_delay = _clamp(float(self.click_delay), 0.0, 60.0)
        self.max_clicks = max(0, int(self.max_clicks))
        self.warmup_frames = int(_clamp(self.warmup_frames, 0, 100))
        self.downscale_max = int(_clamp(self.downscale_max, 16, 1000))
        self.log_history = int(_clamp(self.log_history, 5, 200))
        if self.click_button not in CLICK_BUTTONS:
            self.click_button = "left"
        if self.click_type not in CLICK_TYPES:
            self.click_type = "single"
        if self.compare_mode not in COMPARE_MODES:
            self.compare_mode = "previous"
        if self.theme not in THEME_MODES:
            self.theme = "system"
        if not isinstance(self.hotkey_toggle, str) or not self.hotkey_toggle.strip():
            self.hotkey_toggle = "<ctrl>+<shift>+s"
        if not isinstance(self.hotkey_quit, str) or not self.hotkey_quit.strip():
            self.hotkey_quit = "<ctrl>+<shift>+q"
        return self

    @property
    def is_ready(self) -> bool:
        """True when there is enough info to start monitoring."""
        return (
            self.region is not None
            and self.region.is_valid
            and self.click_x is not None
            and self.click_y is not None
        )

    # -- persistence -------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # asdict turns the nested Region into a dict already (or None).
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        known = {f.name for f in fields(cls)}
        payload = {k: v for k, v in data.items() if k in known}
        region = payload.get("region")
        if isinstance(region, dict):
            payload["region"] = Region(
                int(region["left"]),
                int(region["top"]),
                int(region["width"]),
                int(region["height"]),
            )
        elif region is not None and not isinstance(region, Region):
            payload["region"] = None
        return cls(**payload).clamp()

    def save(self, path: Optional[str] = None) -> str:
        path = path or default_config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Write atomically so a crash mid-write never corrupts the config.
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)
        os.replace(tmp, path)
        return path

    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        path = path or default_config_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return cls.from_dict(json.load(fh))
        except (FileNotFoundError, ValueError, KeyError, TypeError):
            # Missing or corrupt config -> fall back to sane defaults.
            return cls()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
