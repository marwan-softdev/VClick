"""Optional global hotkeys (start/stop without focusing the window).

Uses ``pynput``'s global listener.  This is best-effort: on Wayland the global
listener usually cannot see keystrokes, so failures are swallowed and the GUI
simply works without hotkeys.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional


def pretty(hotkey: str) -> str:
    """Turn a pynput hotkey string like ``<ctrl>+<shift>+s`` into ``Ctrl+Shift+S``."""
    parts = []
    for token in (hotkey or "").split("+"):
        token = token.strip().strip("<>")
        if not token:
            continue
        parts.append(token.upper() if len(token) == 1 else token.capitalize())
    return "+".join(parts) if parts else "(unset)"


def is_valid(hotkey: str) -> bool:
    """A minimal sanity check that a string looks like a usable hotkey."""
    if not isinstance(hotkey, str) or not hotkey.strip():
        return False
    tokens = [t.strip() for t in hotkey.split("+") if t.strip()]
    return len(tokens) >= 1


class HotkeyManager:
    """Registers process-wide hotkeys mapped to callbacks."""

    def __init__(self) -> None:
        self._listener = None
        self.active = False
        self.error: Optional[str] = None

    def start(self, bindings: Dict[str, Callable[[], None]]) -> bool:
        """Start listening. ``bindings`` maps pynput hotkey strings to callables.

        Returns ``True`` if the listener started, ``False`` otherwise (the GUI
        can then hide/grey the hotkey hint).
        """
        try:
            from pynput import keyboard  # lazy import: needs a display

            self._listener = keyboard.GlobalHotKeys(bindings)
            self._listener.start()
            self.active = True
            return True
        except Exception as exc:  # noqa: BLE001 - Wayland / no-perm etc.
            self.error = str(exc)
            self.active = False
            return False

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:  # noqa: BLE001
                pass
            self._listener = None
        self.active = False
