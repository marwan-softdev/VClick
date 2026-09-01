"""Tests for hotkey parsing and the layout/modifier-robust key matching."""

import sys
import threading
import time
import types

import pytest

from vclick import hotkeys
from vclick.hotkeys import (
    HotkeyManager, is_valid, modifier_of, normalize_key, parse_hotkey, pretty,
)


class FakeKeyCode:
    """Stands in for pynput.keyboard.KeyCode."""
    def __init__(self, char=None, vk=None):
        self.char = char
        self.vk = vk


class FakeKey:
    """Stands in for a named pynput.keyboard.Key member."""
    def __init__(self, name):
        self.name = name


# -- parsing ---------------------------------------------------------------
def test_parse_splits_modifiers_and_key():
    assert parse_hotkey("<ctrl>+<shift>+a") == (frozenset({"ctrl", "shift"}), "a")


def test_parse_is_order_independent():
    assert parse_hotkey("<shift>+<ctrl>+a") == parse_hotkey("<ctrl>+<shift>+a")


def test_parse_collapses_left_right_modifiers():
    assert parse_hotkey("<ctrl_l>+a") == parse_hotkey("<ctrl_r>+a") == (frozenset({"ctrl"}), "a")


def test_parse_rejects_modifier_only():
    assert parse_hotkey("<ctrl>+<shift>") is None
    assert parse_hotkey("") is None


def test_pretty_and_valid():
    assert pretty("<ctrl>+<shift>+s") == "Ctrl+Shift+S"
    assert pretty("<alt>+<f5>") == "Alt+F5"
    assert pretty("") == "(unset)"
    assert is_valid("<ctrl>+<shift>+a")
    assert not is_valid("<ctrl>")


# -- the actual bug: Ctrl turns letters into control characters ------------
@pytest.mark.parametrize("ctrl_char,expected", [
    ("\x01", "a"),   # Ctrl+A
    ("\x1a", "z"),   # Ctrl+Z
    ("\x13", "s"),   # Ctrl+S
    ("\x03", "c"),
])
def test_control_characters_map_back_to_letters(ctrl_char, expected):
    # This is what breaks naive matching: '\x01' never equals 'a', so
    # <ctrl>+<shift>+a silently never fires.
    assert normalize_key(FakeKeyCode(char=ctrl_char)) == expected


def test_shifted_letter_is_lowercased():
    assert normalize_key(FakeKeyCode(char="A")) == "a"


def test_plain_letter():
    assert normalize_key(FakeKeyCode(char="a")) == "a"


def test_named_keys():
    assert normalize_key(FakeKey("f5")) == "f5"
    assert normalize_key(FakeKey("space")) == "space"


def test_vk_fallback_when_char_missing():
    assert normalize_key(FakeKeyCode(char=None, vk=65)) == "a"


def test_modifier_detection():
    assert modifier_of(FakeKey("ctrl_l")) == "ctrl"
    assert modifier_of(FakeKey("shift_r")) == "shift"
    assert modifier_of(FakeKey("alt_gr")) == "alt"
    assert modifier_of(FakeKeyCode(char="a")) is None


# -- end-to-end matching without any real keyboard -------------------------
def _press(mgr, *keys):
    for k in keys:
        mgr._on_press(k)


def test_ctrl_shift_letter_fires_even_with_control_char():
    fired = []
    mgr = HotkeyManager()
    mgr._bindings = {parse_hotkey("<ctrl>+<shift>+a"): lambda: fired.append(1)}
    _press(mgr, FakeKey("ctrl_l"), FakeKey("shift_l"), FakeKeyCode(char="\x01"))
    assert fired == [1]


def test_ctrl_shift_z_fires():
    fired = []
    mgr = HotkeyManager()
    mgr._bindings = {parse_hotkey("<ctrl>+<shift>+z"): lambda: fired.append(1)}
    _press(mgr, FakeKey("ctrl_l"), FakeKey("shift_l"), FakeKeyCode(char="\x1a"))
    assert fired == [1]


def test_wrong_modifiers_do_not_fire():
    fired = []
    mgr = HotkeyManager()
    mgr._bindings = {parse_hotkey("<ctrl>+<shift>+a"): lambda: fired.append(1)}
    _press(mgr, FakeKey("ctrl_l"), FakeKeyCode(char="\x01"))  # no shift
    assert fired == []


def test_released_modifier_is_forgotten():
    fired = []
    mgr = HotkeyManager()
    mgr._bindings = {parse_hotkey("<ctrl>+a"): lambda: fired.append(1)}
    mgr._on_press(FakeKey("ctrl_l"))
    mgr._on_release(FakeKey("ctrl_l"))
    mgr._on_press(FakeKeyCode(char="a"))
    assert fired == []


def test_observer_reports_what_was_seen():
    seen = []
    mgr = HotkeyManager()
    mgr.on_observed = seen.append
    _press(mgr, FakeKey("ctrl_l"), FakeKey("shift_l"), FakeKeyCode(char="\x01"))
    assert seen == ["Ctrl+Shift+A"]


def test_callback_error_does_not_propagate():
    mgr = HotkeyManager()
    mgr._bindings = {parse_hotkey("a"): lambda: 1 / 0}
    mgr._on_press(FakeKeyCode(char="a"))  # must not raise


# -- listener startup must never block the caller --------------------------
class _StubListener:
    """Stands in for pynput.keyboard.Listener."""

    def __init__(self, wait_behaviour):
        self._wait_behaviour = wait_behaviour
        self.stopped = False

    def start(self):
        pass

    def wait(self):
        self._wait_behaviour()

    def stop(self):
        self.stopped = True


def _start_with(monkeypatch, listener, timeout=0.3):
    """Run HotkeyManager.start() against *listener* instead of real pynput."""
    monkeypatch.setattr(hotkeys, "READY_TIMEOUT", timeout)
    fake_keyboard = types.SimpleNamespace(Listener=lambda **kw: listener)
    monkeypatch.setitem(sys.modules, "pynput", types.SimpleNamespace(keyboard=fake_keyboard))
    monkeypatch.setitem(sys.modules, "pynput.keyboard", fake_keyboard)
    mgr = HotkeyManager()
    started = time.time()
    ok = mgr.start({"<ctrl>+<shift>+s": lambda: None})
    return mgr, ok, time.time() - started


def test_start_gives_up_on_a_listener_that_never_becomes_ready(monkeypatch):
    """Regression: a wedged listener froze the whole app, close button included.

    HotkeyManager.start() runs on the Tk main loop, and pynput's own
    Listener.wait() has no timeout -- so a listener thread that never
    signalled readiness (it can deadlock against Tk during a GC on that
    thread) hung the main loop forever, leaving a window that wouldn't
    redraw or close. start() must give up and report instead.
    """
    listener = _StubListener(threading.Event().wait)  # never returns
    mgr, ok, elapsed = _start_with(monkeypatch, listener)

    assert ok is False
    assert mgr.active is False
    assert mgr.error and "didn't start" in mgr.error
    assert elapsed < 3, f"start() blocked for {elapsed:.1f}s -- it must be bounded"


def test_start_reports_a_listener_that_fails_outright(monkeypatch):
    def boom():
        raise RuntimeError("no X display")

    mgr, ok, _ = _start_with(monkeypatch, _StubListener(boom))
    assert ok is False
    assert mgr.active is False
    assert "no X display" in (mgr.error or "")


def test_start_succeeds_when_the_listener_comes_up(monkeypatch):
    mgr, ok, _ = _start_with(monkeypatch, _StubListener(lambda: None))
    assert ok is True
    assert mgr.active is True
    assert mgr.error is None


# -- pynput's X11 Mode_switch bug (Shift+letter decoded from the wrong
#    keyboard-layout column on multi-group layouts) ------------------------
class _FakeXorgDisplay:
    """Stands in for the Xlib display object pynput's _find_mask receives."""

    def __init__(self, keycode_of, modifier_mapping):
        self._keycode_of = keycode_of
        self._modifier_mapping = modifier_mapping

    def keysym_to_keycode(self, keysym):
        return self._keycode_of.get(keysym, 0)

    def get_modifier_mapping(self):
        return self._modifier_mapping


def _install_fake_xorg(monkeypatch, find_mask):
    """Inject a stand-in pynput._util.xorg module with the given _find_mask."""
    fake_util = types.ModuleType("pynput._util")
    fake_xorg = types.ModuleType("pynput._util.xorg")
    fake_xorg._find_mask = find_mask
    fake_util.xorg = fake_xorg
    monkeypatch.setitem(sys.modules, "pynput._util", fake_util)
    monkeypatch.setitem(sys.modules, "pynput._util.xorg", fake_xorg)
    return fake_xorg


def _original_find_mask(display, symbol):
    """A faithful copy of pynput's actual (buggy) _find_mask, for testing
    against -- reproduces the real matching behaviour the patch wraps."""
    import Xlib.XK
    modifier_keycode = display.keysym_to_keycode(Xlib.XK.string_to_keysym(symbol))
    for index, keycodes in enumerate(display.get_modifier_mapping()):
        for keycode in keycodes:
            if keycode == modifier_keycode:
                return 1 << index
    return 0


def test_unbound_mode_switch_no_longer_aliases_to_shift(monkeypatch):
    """Regression: this is the exact shape of a real 'us,ara,us' X server.

    Mode_switch is bound to no key (keycode 0), and the Shift row of the
    server's modifier map is zero-padded out to 4 slots (only 2 physical
    keys -- Shift_L/Shift_R -- are actually bound). The unpatched lookup
    matches keycode 0 against that padding and calls the result "AltGr",
    which pynput's shift_to_index then folds into every Shift-held keypress
    -- verified directly against the real modifier map captured from such
    a display.
    """
    display = _FakeXorgDisplay(
        keycode_of={},  # Mode_switch: unbound anywhere
        modifier_mapping=[[50, 62, 0, 0], [66, 0, 0, 0], [37, 105, 0, 0]],
    )
    # Sanity check: the bug is real in the function being wrapped.
    assert _original_find_mask(display, "Mode_switch") == 1  # aliased to Shift

    fake_xorg = _install_fake_xorg(monkeypatch, _original_find_mask)
    hotkeys._patch_pynput_mode_switch()

    assert fake_xorg._find_mask(display, "Mode_switch") == 0


def test_a_genuinely_bound_altgr_key_is_unaffected(monkeypatch):
    """A layout that *does* bind Mode_switch to a real key must decode the
    same as before -- this patch only changes the unbound case."""
    display = _FakeXorgDisplay(
        keycode_of={ord: 92 for ord in (65406,)},  # some keysym -> keycode 92
        modifier_mapping=[[50, 62, 0, 0], [66, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0],
                           [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [92, 0, 0, 0]],
    )
    fake_xorg = _install_fake_xorg(monkeypatch, _original_find_mask)
    hotkeys._patch_pynput_mode_switch()

    assert fake_xorg._find_mask(display, "Mode_switch") == 1 << 7


def test_patch_is_idempotent(monkeypatch):
    """start() calls this on every hotkey change -- must not double-wrap."""
    fake_xorg = _install_fake_xorg(monkeypatch, _original_find_mask)
    hotkeys._patch_pynput_mode_switch()
    once = fake_xorg._find_mask
    hotkeys._patch_pynput_mode_switch()
    assert fake_xorg._find_mask is once


def test_missing_pynput_internals_is_a_silent_no_op(monkeypatch):
    """If pynput's X11 backend can't even be imported (no display, non-X11
    platform), there is nothing to patch -- must not raise."""
    monkeypatch.delitem(sys.modules, "pynput._util", raising=False)
    monkeypatch.delitem(sys.modules, "pynput._util.xorg", raising=False)
    real_import = __import__

    def blocked(name, *a, **kw):
        if name.startswith("pynput"):
            raise ImportError("no X11 backend here")
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", blocked)
    hotkeys._patch_pynput_mode_switch()  # must not raise
