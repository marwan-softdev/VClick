"""Tests for the follow-up features: change mask, preview, hotkeys, config."""

import base64

import numpy as np

from screenwatch.capture import build_change_preview
from screenwatch.config import Config
from screenwatch.detector import ChangeDetector
from screenwatch.hotkeys import is_valid, pretty


# -- detector: keep the "what changed" mask --------------------------------
def test_detector_keeps_mask_when_requested():
    det = ChangeDetector(sensitivity=50, pixel_threshold=10, keep_mask=True)
    det.process(np.zeros((20, 20), dtype=np.int16))
    frame = np.zeros((20, 20), dtype=np.int16)
    frame[:5, :] = 255  # top quarter changes
    res = det.process(frame)
    assert res.changed
    assert det.last_mask is not None
    assert det.last_mask.shape == (20, 20)
    assert det.last_mask[:5, :].all()
    assert not det.last_mask[6:, :].any()


def test_detector_drops_mask_by_default():
    det = ChangeDetector(sensitivity=50, keep_mask=False)
    det.process(np.zeros((10, 10), dtype=np.int16))
    det.process(np.full((10, 10), 255, dtype=np.int16))
    assert det.last_mask is None


def test_keep_mask_toggles_live():
    det = ChangeDetector(sensitivity=50, keep_mask=False)
    det.update_settings(50, 25, "previous", keep_mask=True)
    assert det.keep_mask is True
    det.update_settings(50, 25, "previous")  # unspecified leaves it on
    assert det.keep_mask is True


# -- capture: the "why" preview image --------------------------------------
def test_build_change_preview_returns_png():
    w, h = 40, 30
    raw = (np.random.rand(h, w, 4) * 255).astype(np.uint8).tobytes()
    mask = np.zeros((15, 20), dtype=bool)
    mask[:5, :5] = True
    data = build_change_preview(raw, w, h, mask, out_max=120)
    assert isinstance(data, str)
    decoded = base64.b64decode(data)
    assert decoded[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic number


# -- hotkeys: display + validation -----------------------------------------
def test_pretty_formats_hotkey():
    assert pretty("<ctrl>+<shift>+s") == "Ctrl+Shift+S"
    assert pretty("<cmd>+<f5>") == "Cmd+F5"
    assert pretty("") == "(unset)"


def test_is_valid_hotkey():
    assert is_valid("<ctrl>+<shift>+s")
    assert is_valid("<f5>")
    assert not is_valid("")
    assert not is_valid("   ")
    assert not is_valid(None)


# -- config: new fields persist and validate -------------------------------
def test_new_fields_roundtrip():
    c = Config(hotkey_toggle="<ctrl>+a", hotkey_quit="<ctrl>+b",
               hotkeys_enabled=False, show_detection_preview=False)
    restored = Config.from_dict(c.to_dict())
    assert restored.hotkey_toggle == "<ctrl>+a"
    assert restored.hotkey_quit == "<ctrl>+b"
    assert restored.hotkeys_enabled is False
    assert restored.show_detection_preview is False


def test_clamp_repairs_blank_hotkeys():
    c = Config(hotkey_toggle="", hotkey_quit="   ")
    c.clamp()
    assert c.hotkey_toggle == "<ctrl>+<shift>+s"
    assert c.hotkey_quit == "<ctrl>+<shift>+q"


def test_gui_keysym_mapping_is_importable_headlessly():
    # gui.py must not import tkinter/pynput at module load.
    from screenwatch.gui import _keysym_to_token

    assert _keysym_to_token("S") == "s"
    assert _keysym_to_token("F5") == "<f5>"
    assert _keysym_to_token("Return") == "<enter>"
    assert _keysym_to_token("space") == "<space>"
    assert _keysym_to_token("Control_L") is None
