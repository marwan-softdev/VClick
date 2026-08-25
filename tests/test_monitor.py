"""End-to-end test of the capture→detect→click loop with fakes (headless).

This drives the real :class:`Monitor` thread; only the screen grab (``mss``) and
the mouse (``Clicker``) are faked, so the detection/pacing/cooldown logic runs
exactly as it would on a real desktop.
"""

import sys
import threading
import time
import types

import numpy as np

from vclick.config import Config, Region
from vclick.monitor import Monitor


def _solid_bgra(value, w, h):
    px = np.array([value, value, value, 255], dtype=np.uint8)
    return np.tile(px, w * h).tobytes()


class _FakeShot:
    def __init__(self, raw, w, h):
        self.raw, self.width, self.height = raw, w, h


class _FakeSct:
    """A stand-in for ``mss.mss()`` that yields a scripted sequence of frames."""

    def __init__(self, frames):
        self._frames = frames
        self._i = 0
        self.monitors = [{"left": 0, "top": 0, "width": 100, "height": 100}]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def grab(self, box):
        frame = self._frames[min(self._i, len(self._frames) - 1)]
        self._i += 1
        return frame


def _install_fake_mss(monkeypatch, frames):
    module = types.ModuleType("mss")
    module.mss = lambda: _FakeSct(frames)
    monkeypatch.setitem(sys.modules, "mss", module)


class _RecordingClicker:
    def __init__(self):
        self.clicks = []

    def click(self, x, y, button="left", double=False):
        self.clicks.append((x, y, button, double))


def _run_until(monitor, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_click_fires_when_region_changes(monkeypatch):
    w = h = 10
    a = _FakeShot(_solid_bgra(0, w, h), w, h)      # baseline
    b = _FakeShot(_solid_bgra(255, w, h), w, h)    # big change
    _install_fake_mss(monkeypatch, [a, a, b, b])

    cfg = Config(
        region=Region(0, 0, w, h),
        click_x=42, click_y=24,
        fps=50, sensitivity=90, pixel_threshold=10,
        cooldown=0, warmup_frames=1, max_clicks=1,
    ).clamp()

    events = []
    clicker = _RecordingClicker()
    mon = Monitor(cfg, on_event=events.append, clicker=clicker)
    mon.start()

    assert _run_until(mon, lambda: len(clicker.clicks) >= 1), "no click was fired"
    mon.stop()

    assert clicker.clicks[0] == (42, 24, "left", False)
    assert any(e.kind == "clicked" for e in events)
    assert any(e.kind == "limit" for e in events)  # max_clicks honoured


def test_no_click_when_region_is_static(monkeypatch):
    w = h = 10
    still = _FakeShot(_solid_bgra(128, w, h), w, h)
    _install_fake_mss(monkeypatch, [still] * 6)

    cfg = Config(
        region=Region(0, 0, w, h),
        click_x=1, click_y=1,
        fps=50, sensitivity=100, pixel_threshold=5,
        cooldown=0, warmup_frames=1,
    ).clamp()

    clicker = _RecordingClicker()
    mon = Monitor(cfg, on_event=lambda e: None, clicker=clicker)
    mon.start()
    time.sleep(0.4)
    mon.stop()

    assert clicker.clicks == []


def test_cooldown_limits_click_rate(monkeypatch):
    w = h = 10
    # Alternate frames forever so a change is available on most iterations.
    a = _FakeShot(_solid_bgra(0, w, h), w, h)
    b = _FakeShot(_solid_bgra(255, w, h), w, h)
    _install_fake_mss(monkeypatch, [a, b] * 200)

    cfg = Config(
        region=Region(0, 0, w, h),
        click_x=1, click_y=1,
        fps=100, sensitivity=90, pixel_threshold=10,
        cooldown=0.25, warmup_frames=1,
    ).clamp()

    clicker = _RecordingClicker()
    mon = Monitor(cfg, on_event=lambda e: None, clicker=clicker)
    mon.start()
    time.sleep(0.6)
    mon.stop()

    # ~0.6s with a 0.25s cooldown => at most 3 clicks, comfortably not dozens.
    assert 1 <= len(clicker.clicks) <= 4


def test_stop_is_prompt(monkeypatch):
    w = h = 10
    still = _FakeShot(_solid_bgra(50, w, h), w, h)
    _install_fake_mss(monkeypatch, [still] * 1000)

    cfg = Config(region=Region(0, 0, w, h), click_x=1, click_y=1, fps=2).clamp()
    mon = Monitor(cfg, on_event=lambda e: None, clicker=_RecordingClicker())
    mon.start()
    time.sleep(0.1)
    t0 = time.monotonic()
    mon.stop()
    # Even at 2 fps (0.5s/frame), stop() must not block for a whole frame.
    assert time.monotonic() - t0 < 0.3
    assert not mon.is_running
