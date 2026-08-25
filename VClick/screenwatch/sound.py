"""Audible click feedback.

``print("\\a")`` only writes a BEL character to stdout: it does nothing when the
app is launched from a desktop icon (no terminal attached), and most terminal
emulators ship with the bell disabled anyway.  So we try real audio players in
order and remember the first one that works.

On Windows, the stdlib ``winsound`` module plays a system notification sound
directly (no external player needed) and is tried first.  On Linux we shell
out to whichever of a handful of common CLI players is installed.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import List, Optional, Tuple

# Ordered candidates: (executable, args-builder).  The first that exists and
# exits cleanly is reused for the rest of the session.
_FREEDESKTOP_SOUNDS = (
    "/usr/share/sounds/freedesktop/stereo/message.oga",
    "/usr/share/sounds/freedesktop/stereo/bell.oga",
    "/usr/share/sounds/freedesktop/stereo/complete.oga",
)


def _existing_sound() -> Optional[str]:
    import os

    for path in _FREEDESKTOP_SOUNDS:
        if os.path.exists(path):
            return path
    return None


def _candidates() -> List[Tuple[str, List[str]]]:
    cands: List[Tuple[str, List[str]]] = []
    if shutil.which("canberra-gtk-play"):
        cands.append(("canberra-gtk-play", ["canberra-gtk-play", "-i", "message"]))
    sound = _existing_sound()
    if sound:
        if shutil.which("paplay"):
            cands.append(("paplay", ["paplay", sound]))
        if shutil.which("pw-play"):
            cands.append(("pw-play", ["pw-play", sound]))
        if shutil.which("ffplay"):
            cands.append(("ffplay", ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", sound]))
    if shutil.which("aplay"):
        wav = "/usr/share/sounds/alsa/Front_Center.wav"
        import os

        if os.path.exists(wav):
            cands.append(("aplay", ["aplay", "-q", wav]))
    return cands


class Beeper:
    """Plays a short notification sound, with graceful degradation.

    Resolution happens once, lazily; afterwards playing is a single
    non-blocking ``Popen``.  If nothing works, :attr:`backend` is ``"none"`` so
    the GUI can tell the user instead of silently doing nothing.
    """

    def __init__(self, tk_widget=None) -> None:
        self._cmd: Optional[List[str]] = None
        self._winsound = None
        self._resolved = False
        self.backend = "unresolved"
        self._tk_widget = tk_widget

    def _resolve(self) -> None:
        if self._resolved:
            return
        self._resolved = True

        if sys.platform == "win32":
            try:
                import winsound  # stdlib, Windows only

                self._winsound = winsound
                self.backend = "winsound"
                return
            except ImportError:  # pragma: no cover - always present on Windows
                pass

        for name, cmd in _candidates():
            try:
                subprocess.run(cmd, timeout=5, check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:  # noqa: BLE001 - try the next candidate
                continue
            self._cmd, self.backend = cmd, name
            return
        # Last resort: the system bell via Tk. Often disabled, but free to try.
        self.backend = "tk-bell" if self._tk_widget is not None else "none"

    def play(self) -> None:
        """Fire and forget; never raises and never blocks the caller."""
        self._resolve()
        if self._winsound is not None:
            try:
                # Asynchronous + non-blocking: returns immediately, never
                # stalls the monitor loop waiting on Windows' audio mixer.
                self._winsound.MessageBeep(self._winsound.MB_ICONASTERISK)
            except Exception:  # noqa: BLE001
                pass
            return
        if self._cmd is not None:
            try:
                subprocess.Popen(self._cmd, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return
            except Exception:  # noqa: BLE001
                pass
        if self._tk_widget is not None:
            try:
                self._tk_widget.bell()
            except Exception:  # noqa: BLE001
                pass
