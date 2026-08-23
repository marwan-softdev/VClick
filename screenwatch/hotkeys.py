"""Global hotkeys with layout- and modifier-robust matching.

pynput ships :class:`pynput.keyboard.GlobalHotKeys`, but it matches on the
*character* the key produced.  That is fragile for combinations involving
Ctrl, because many X servers deliver a **control character** instead of the
letter: holding Ctrl and pressing ``a`` arrives as ``'\\x01'``, ``z`` as
``'\\x1a'``.  Those never equal ``'a'``/``'z'``, so ``<ctrl>+<shift>+a`` looks
"registered" yet never fires, while a bare ``a`` works fine.  Shifted letters
(``'A'`` vs ``'a'``) and non-Latin layouts cause the same class of mismatch.

So we do the matching ourselves:

* modifier keys are tracked as a set of canonical names (``ctrl``/``shift``/
  ``alt``/``cmd``), collapsing the left/right variants;
* the trigger key is reduced to a token by :func:`normalize_key`, which undoes
  the control-character mapping, lowercases, and falls back to pynput's own
  ``canonical()`` and to the virtual key code.

:func:`normalize_key` is pure and unit-tested, including the control-character
case that a virtual X server does not reproduce.
"""

from __future__ import annotations

from typing import Callable, Dict, FrozenSet, Optional, Set, Tuple

# Canonical modifier names, and the pynput Key names that map onto them.
_MOD_ALIASES = {
    "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl", "control": "ctrl",
    "shift": "shift", "shift_l": "shift", "shift_r": "shift",
    "alt": "alt", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
    "cmd": "cmd", "cmd_l": "cmd", "cmd_r": "cmd", "super": "cmd", "win": "cmd",
}

ParsedHotkey = Tuple[FrozenSet[str], str]


def parse_hotkey(hotkey: str) -> Optional[ParsedHotkey]:
    """``"<ctrl>+<shift>+a"`` -> ``(frozenset({"ctrl","shift"}), "a")``.

    Returns ``None`` when the string has no non-modifier key to trigger on.
    """
    mods: Set[str] = set()
    key: Optional[str] = None
    for raw in (hotkey or "").split("+"):
        token = raw.strip().strip("<>").lower()
        if not token:
            continue
        if token in _MOD_ALIASES:
            mods.add(_MOD_ALIASES[token])
        else:
            key = token
    if key is None:
        return None
    return frozenset(mods), key


def normalize_key(key, listener=None) -> Optional[str]:
    """Reduce a pynput key event to a comparable token such as ``a`` or ``f5``.

    Handles the cases that break naive character matching:

    * ``Ctrl`` turning a letter into a control character (``'\\x01'`` -> ``a``);
    * ``Shift`` uppercasing it (``'A'`` -> ``a``);
    * named keys (``Key.f5`` -> ``f5``, ``Key.space`` -> ``space``).
    """
    # Named keys (function keys, space, enter, arrows...) expose ``name``.
    name = getattr(key, "name", None)
    if name:
        name = name.lower()
        return _MOD_ALIASES.get(name, name)

    char = getattr(key, "char", None)
    if char:
        # Ctrl+letter arrives as a C0 control character on many X setups.
        if len(char) == 1 and ord(char) < 32:
            mapped = chr(ord(char) + 96)
            if mapped.isalpha():
                return mapped
        return char.lower()

    # char is None (dead keys, some layouts): try pynput's own canonical form,
    # then the virtual key code as a last resort.
    if listener is not None:
        try:
            canon = listener.canonical(key)
        except Exception:  # noqa: BLE001
            canon = None
        if canon is not None and canon is not key:
            canon_char = getattr(canon, "char", None)
            if canon_char:
                return canon_char.lower()
            canon_name = getattr(canon, "name", None)
            if canon_name:
                return canon_name.lower()

    vk = getattr(key, "vk", None)
    if vk is not None:
        # Letter/digit virtual keys map onto their ASCII character.
        if 65 <= vk <= 90 or 97 <= vk <= 122 or 48 <= vk <= 57:
            return chr(vk).lower()
        return f"vk{vk}"
    return None


def modifier_of(key) -> Optional[str]:
    """Return ``ctrl``/``shift``/``alt``/``cmd`` if *key* is a modifier."""
    name = getattr(key, "name", None)
    if not name:
        return None
    return _MOD_ALIASES.get(name.lower())


def _display_key(key: str) -> str:
    """Render a matching token for display.

    Most tokens are a single character or a named key ("f5", "space") and
    just need capitalizing. The one exception is :func:`normalize_key`'s
    last-resort fallback, a raw ``vk<code>`` virtual-key/keysym number for a
    key it couldn't otherwise identify -- shown verbatim that reads as an
    internal error ("Vk65301"), not a key name, so it's reworded into an
    honest "unrecognized key" label instead.
    """
    if len(key) == 1:
        return key.upper()
    if key.startswith("vk") and key[2:].isdigit():
        return f"Unknown key ({key[2:]})"
    return key.capitalize()


def pretty(hotkey: str) -> str:
    """``"<ctrl>+<shift>+s"`` -> ``"Ctrl+Shift+S"`` for display."""
    parsed = parse_hotkey(hotkey)
    if parsed is None:
        return "(unset)"
    mods, key = parsed
    order = [m for m in ("ctrl", "alt", "shift", "cmd") if m in mods]
    parts = [m.capitalize() for m in order]
    parts.append(_display_key(key))
    return "+".join(parts)


def is_valid(hotkey: str) -> bool:
    """True when the string names a usable trigger key."""
    return parse_hotkey(hotkey) is not None


class HotkeyManager:
    """Listens globally and invokes callbacks on matching combinations."""

    def __init__(self) -> None:
        self._listener = None
        self._bindings: Dict[ParsedHotkey, Callable[[], None]] = {}
        self._down: Set[str] = set()
        self.active = False
        self.error: Optional[str] = None
        # Optional hook: called with a human-readable combo for every key
        # press, so the UI can show what the listener actually receives.
        self.on_observed: Optional[Callable[[str], None]] = None

    # -- lifecycle ---------------------------------------------------------
    def start(self, bindings: Dict[str, Callable[[], None]]) -> bool:
        """Begin listening. Returns ``False`` if a listener cannot be created."""
        self.stop()
        self._bindings = {}
        for combo, callback in bindings.items():
            parsed = parse_hotkey(combo)
            if parsed is not None:
                self._bindings[parsed] = callback
        if not self._bindings:
            self.error = "no valid hotkeys"
            return False
        try:
            from pynput import keyboard  # lazy import: needs a display

            self._listener = keyboard.Listener(
                on_press=self._on_press, on_release=self._on_release)
            self._listener.start()
            self._listener.wait()
            self.active = True
            self.error = None
            return True
        except Exception as exc:  # noqa: BLE001 - Wayland / no perms / no X
            self.error = str(exc)
            self.active = False
            self._listener = None
            return False

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:  # noqa: BLE001
                pass
            self._listener = None
        self._down.clear()
        self.active = False

    # -- event handling ----------------------------------------------------
    def _on_press(self, key) -> None:
        mod = modifier_of(key)
        if mod:
            self._down.add(mod)
            return
        token = normalize_key(key, self._listener)
        if token is None:
            return
        held = frozenset(self._down)
        if self.on_observed is not None:
            try:
                self.on_observed(_describe(held, token))
            except Exception:  # noqa: BLE001 - observers must never break input
                pass
        callback = self._bindings.get((held, token))
        if callback is not None:
            try:
                callback()
            except Exception:  # noqa: BLE001 - a bad callback must not kill us
                pass

    def _on_release(self, key) -> None:
        mod = modifier_of(key)
        if mod:
            self._down.discard(mod)


def _describe(mods: FrozenSet[str], key: str) -> str:
    order = [m for m in ("ctrl", "alt", "shift", "cmd") if m in mods]
    parts = [m.capitalize() for m in order]
    parts.append(_display_key(key))
    return "+".join(parts)
