"""The monitoring worker thread.

:class:`Monitor` owns the capture → detect → click loop.  It runs in its own
thread and reports events back to the GUI through a plain callback (the GUI
marshals those onto the Tk main loop).  It is written to be gentle on the CPU:

* the region is captured at a bounded FPS (``time`` based pacing, never a busy
  loop);
* frames are down-sampled to a tiny colour array before any comparison;
* ``mss`` is created *inside* the thread because it is not shareable across
  threads.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .capture import build_change_preview, to_color_samples
from .clicker import Clicker
from .config import Config
from .detector import ChangeDetector


@dataclass
class MonitorEvent:
    """Something worth telling the GUI about."""

    kind: str  # "started" | "stopped" | "clicked" | "tick" | "error" | "limit"
    message: str = ""
    score: float = 0.0
    clicks: int = 0
    elapsed: float = 0.0
    preview: Optional[str] = None  # base64 PNG explaining a detected change


EventCallback = Callable[[MonitorEvent], None]


class Monitor:
    """Start/stop a background thread that watches a region and clicks."""

    def __init__(self, config: Config, on_event: EventCallback, clicker: Optional[Clicker] = None) -> None:
        self._config = config
        self._on_event = on_event
        self._clicker = clicker or Clicker()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._clicks = 0
        self._started_at = 0.0
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        if not self._config.is_ready:
            self._emit(MonitorEvent("error", "Select a region and a click point first."))
            return
        self._stop.clear()
        self._clicks = 0
        self._thread = threading.Thread(target=self._run, name="vclick-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None

    # -- the loop ----------------------------------------------------------
    def _run(self) -> None:
        cfg = self._config
        import mss  # lazy: keeps the module importable without a display

        detector = ChangeDetector(
            cfg.sensitivity, cfg.pixel_threshold, cfg.compare_mode,
            keep_mask=cfg.show_detection_preview,
        )
        monitor_box = cfg.region.as_mss_monitor()
        self._started_at = time.monotonic()
        last_click = 0.0
        frame_index = 0

        self._emit(MonitorEvent("started", f"Watching {cfg.region}", elapsed=0.0))
        try:
            with mss.mss() as sct:
                while not self._stop.is_set():
                    frame_start = time.monotonic()
                    period = 1.0 / max(0.5, cfg.fps)

                    # Live-apply any settings the GUI changed while running.
                    detector.update_settings(
                        cfg.sensitivity, cfg.pixel_threshold, cfg.compare_mode,
                        keep_mask=cfg.show_detection_preview,
                    )

                    shot = sct.grab(monitor_box)
                    frame = to_color_samples(shot.raw, shot.width, shot.height, cfg.downscale_max)
                    # The mask belongs to the pre-advance reference, so capture
                    # it right after process() while shot still holds this frame.
                    result = detector.process(frame)
                    change_mask = detector.last_mask
                    frame_index += 1

                    now = time.monotonic()
                    warm = frame_index > cfg.warmup_frames
                    cooled = (now - last_click) >= cfg.cooldown

                    if result.changed and warm and cooled:
                        if cfg.click_delay > 0:
                            # Interruptible delay.
                            if self._stop.wait(cfg.click_delay):
                                break
                        preview = None
                        if cfg.show_detection_preview and change_mask is not None:
                            try:
                                preview = build_change_preview(
                                    shot.raw, shot.width, shot.height, change_mask
                                )
                            except Exception:  # noqa: BLE001 - preview is optional
                                preview = None
                        self._do_click(cfg)
                        self._clicks += 1
                        last_click = time.monotonic()
                        # The click itself changes the screen; forget the
                        # reference so its visual echo does not re-trigger us.
                        detector.reset()
                        self._emit(
                            MonitorEvent(
                                "clicked",
                                f"Change detected ({result.score * 100:.2f}%) → clicked",
                                score=result.score,
                                clicks=self._clicks,
                                elapsed=now - self._started_at,
                                preview=preview,
                            )
                        )
                        if cfg.max_clicks and self._clicks >= cfg.max_clicks:
                            self._emit(MonitorEvent("limit", "Reached click limit — stopping.", clicks=self._clicks))
                            break
                    else:
                        self._emit(
                            MonitorEvent(
                                "tick",
                                score=result.score,
                                clicks=self._clicks,
                                elapsed=now - self._started_at,
                            )
                        )

                    # Pace the loop; sleep the remainder of this frame's budget.
                    elapsed = time.monotonic() - frame_start
                    remaining = period - elapsed
                    if remaining > 0:
                        # Use the stop-event as the sleeper so stop() is instant.
                        if self._stop.wait(remaining):
                            break
        except Exception as exc:  # noqa: BLE001 - surface any runtime failure
            self._emit(MonitorEvent("error", f"Monitoring stopped: {exc}"))
        finally:
            self._emit(
                MonitorEvent(
                    "stopped",
                    "Stopped.",
                    clicks=self._clicks,
                    elapsed=time.monotonic() - self._started_at,
                )
            )

    def _do_click(self, cfg: Config) -> None:
        self._clicker.click(
            cfg.click_x,
            cfg.click_y,
            button=cfg.click_button,
            double=(cfg.click_type == "double"),
        )
        # Audible feedback is raised by the GUI (see VClickApp), which owns
        # a Beeper and can fall back to the Tk bell; doing it here would mean
        # writing BEL to a stdout nobody is watching.

    def _emit(self, event: MonitorEvent) -> None:
        try:
            self._on_event(event)
        except Exception:  # noqa: BLE001 - never let a UI callback kill the loop
            pass
