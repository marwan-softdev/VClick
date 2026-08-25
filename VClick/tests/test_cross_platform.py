"""Cross-platform behaviour: config path, sound backend, and bundled icon.

This machine only runs Linux, so Windows-specific branches are exercised by
monkeypatching ``sys.platform`` and, where needed, injecting a stand-in for
the stdlib ``winsound`` module (which does not exist off Windows). The logic
under test is exactly what runs for real on Windows; only the OS identity and
the presence of ``winsound`` are simulated.
"""

import os
import sys

import pytest

from screenwatch.config import default_config_path
from screenwatch.paths import icon_ico_path, icon_path
from screenwatch.sound import Beeper


# -- config path -------------------------------------------------------------
# Note: os.path.join's separator is bound to the interpreter's REAL OS (which
# posixpath/ntpath module got loaded at startup), not to a monkeypatched
# sys.platform -- so on this Linux test machine, even a simulated "win32"
# still joins with "/". That's a property of testing platform code on the
# "wrong" platform, not a bug: on genuine Windows sys.platform is really
# "win32" and os.path really is ntpath, so it does produce backslashes. These
# tests therefore build expectations with os.path.join too, so they check the
# *logic* (which base directory, which subfolder) rather than hard-coding a
# separator this machine cannot actually produce.
def test_windows_config_path_uses_appdata(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    appdata = os.path.join("C:", "Users", "Test", "AppData", "Roaming")
    monkeypatch.setenv("APPDATA", appdata)
    path = default_config_path()
    assert path == os.path.join(appdata, "ScreenWatch", "config.json")


def test_windows_config_path_falls_back_without_appdata(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    path = default_config_path()
    assert path.endswith(os.path.join("ScreenWatch", "config.json"))


def test_linux_config_path_still_uses_xdg(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/home/test/.config")
    path = default_config_path()
    assert path == "/home/test/.config/screenwatch/config.json"


def test_linux_config_path_default_without_xdg(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", "/home/test")
    path = default_config_path()
    assert path == "/home/test/.config/screenwatch/config.json"


# -- sound backend ------------------------------------------------------------
class _FakeWinsound:
    MB_ICONASTERISK = 0x40
    calls = []

    @classmethod
    def MessageBeep(cls, kind):
        cls.calls.append(kind)


def test_windows_beeper_resolves_to_winsound(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winsound", _FakeWinsound)
    _FakeWinsound.calls.clear()

    b = Beeper()
    b._resolve()
    assert b.backend == "winsound"

    b.play()
    assert _FakeWinsound.calls == [_FakeWinsound.MB_ICONASTERISK]


def test_windows_beeper_never_shells_out_to_linux_tools(monkeypatch):
    # On win32 the Linux CLI-player search must never even run.
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winsound", _FakeWinsound)

    import screenwatch.sound as sound_mod

    def _boom():
        raise AssertionError("must not search for Linux audio players on Windows")

    monkeypatch.setattr(sound_mod, "_candidates", _boom)
    b = Beeper()
    b._resolve()  # must not raise
    assert b.backend == "winsound"


def test_beeper_falls_back_to_tk_bell_when_nothing_else_works(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    import screenwatch.sound as sound_mod

    monkeypatch.setattr(sound_mod, "_candidates", lambda: [])

    class FakeWidget:
        rang = False

        def bell(self):
            self.rang = True

    widget = FakeWidget()
    b = Beeper(widget)
    b.play()
    assert b.backend == "tk-bell"
    assert widget.rang is True


def test_beeper_with_no_widget_and_no_backend_is_silent_and_safe(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    import screenwatch.sound as sound_mod

    monkeypatch.setattr(sound_mod, "_candidates", lambda: [])
    b = Beeper(None)
    b.play()  # must not raise
    assert b.backend == "none"


# -- bundled icon --------------------------------------------------------------
def test_icon_png_is_packaged_and_valid():
    path = icon_path()
    assert path is not None and path.endswith("icon.png")
    PIL_Image = pytest.importorskip("PIL.Image")
    img = PIL_Image.open(path)
    assert img.size[0] > 0 and img.size[1] > 0


def test_icon_ico_is_packaged_and_multi_size():
    path = icon_ico_path()
    assert path is not None and path.endswith("icon.ico")
    PIL_Image = pytest.importorskip("PIL.Image")
    ico = PIL_Image.open(path)
    sizes = ico.info.get("sizes", set())
    # Windows shortcuts/taskbar pick different sizes at different DPIs/zoom
    # levels; a single-resolution .ico looks blurry when scaled.
    assert len(sizes) >= 4
    assert (256, 256) in sizes or max(sizes)[0] >= 128
