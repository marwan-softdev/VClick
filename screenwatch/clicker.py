"""Mouse-click backend.

``pynput`` is the primary backend (pure-Python, lightweight).  Because it needs
a display *at import time*, it is imported lazily so the rest of the package
stays testable on headless machines.

For Wayland sessions — where pynput's X backend cannot synthesise input — the
clicker transparently falls back to the ``ydotool`` command-line tool if it is
installed, and to ``xdotool`` for XWayland/X11 setups.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Optional


class ClickError(RuntimeError):
    """Raised when no working click backend is available."""


class Clicker:
    """Clicks a screen coordinate using the best available backend.

    The backend is resolved once on first use and reused thereafter, so the
    hot path stays cheap during long sessions.
    """

    def __init__(self) -> None:
        self._backend: Optional[str] = None
        self._mouse = None  # pynput controller, created lazily
        self._button_map: dict = {}

    # -- backend resolution ------------------------------------------------
    def _ensure_backend(self) -> None:
        if self._backend is not None:
            return
        # 1) pynput — best cross-desktop experience on X11.
        try:
            from pynput.mouse import Button, Controller  # type: ignore

            self._mouse = Controller()
            self._button_map = {
                "left": Button.left,
                "right": Button.right,
                "middle": Button.middle,
            }
            self._backend = "pynput"
            return
        except Exception:  # noqa: BLE001 - any failure means try the next one
            self._mouse = None

        # 2) ydotool — works on native Wayland (needs ydotoold running).
        if shutil.which("ydotool"):
            self._backend = "ydotool"
            return

        # 3) xdotool — classic X11 CLI tool.
        if shutil.which("xdotool"):
            self._backend = "xdotool"
            return

        raise ClickError(
            "No click backend available. Install python3 'pynput' (X11) or the "
            "'ydotool' (Wayland) / 'xdotool' (X11) command-line tools."
        )

    @property
    def backend_name(self) -> str:
        try:
            self._ensure_backend()
        except ClickError:
            return "none"
        return self._backend or "none"

    # -- clicking ----------------------------------------------------------
    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        double: bool = False,
    ) -> None:
        """Move to ``(x, y)`` and click. Restores the original cursor position."""
        self._ensure_backend()
        if self._backend == "pynput":
            self._click_pynput(x, y, button, double)
        elif self._backend == "ydotool":
            self._click_ydotool(x, y, button, double)
        elif self._backend == "xdotool":
            self._click_xdotool(x, y, button, double)

    def _click_pynput(self, x: int, y: int, button: str, double: bool) -> None:
        btn = self._button_map.get(button, self._button_map["left"])
        original = self._mouse.position
        self._mouse.position = (x, y)
        # Tiny settle so the compositor registers the move before the click.
        time.sleep(0.01)
        self._mouse.click(btn, 2 if double else 1)
        # Return the pointer so we don't disturb whatever the user is doing.
        try:
            self._mouse.position = original
        except Exception:  # noqa: BLE001 - restoring is best-effort
            pass

    def _click_xdotool(self, x: int, y: int, button: str, double: bool) -> None:
        code = {"left": "1", "right": "3", "middle": "2"}.get(button, "1")
        args = ["xdotool", "mousemove", str(x), str(y), "click"]
        if double:
            args += ["--repeat", "2"]
        args.append(code)
        subprocess.run(args, check=False)

    def _click_ydotool(self, x: int, y: int, button: str, double: bool) -> None:
        # ydotool uses absolute-move then a button chord (0x40=press,0x80=release).
        code = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}.get(button, "0xC0")
        subprocess.run(["ydotool", "mousemove", "--absolute", "-x", str(x), "-y", str(y)], check=False)
        subprocess.run(["ydotool", "click", code], check=False)
        if double:
            subprocess.run(["ydotool", "click", code], check=False)
