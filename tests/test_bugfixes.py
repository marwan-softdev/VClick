"""Regression tests for reported bugs: highlight visibility, ids, sound."""

import base64
import io

import numpy as np
import pytest

from screenwatch.capture import build_change_preview
from screenwatch.history import DetectionHistory
from screenwatch.sound import Beeper

PIL = pytest.importorskip("PIL.Image")


def _render(mask, sprite_bgr=(0, 165, 255)):
    w, h = 120, 90
    img = np.full((h, w, 4), 255, np.uint8)
    img[30:70, 40:100] = [*sprite_bgr, 255]
    png = build_change_preview(img.tobytes(), w, h, mask, out_max=120)
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(base64.b64decode(png))).convert("RGB")).astype(int)


def test_unchanged_pixels_are_desaturated_grey():
    # A red tint over already-warm content was invisible; unchanged content is
    # now greyscale so any highlight stands out.
    mask = np.zeros((45, 60), dtype=bool)
    mask[5:10, 5:10] = True
    out = _render(mask)
    px = out[40, 20]  # over the orange sprite, but NOT in the changed area
    assert max(px) - min(px) <= 2, f"expected grey, got {tuple(px)}"


def test_changed_pixels_are_strongly_red_even_over_orange():
    mask = np.zeros((45, 60), dtype=bool)
    mask[15:35, 20:50] = True  # covers the orange sprite
    out = _render(mask)
    px = out[45, 60]
    redness = px[0] - max(px[1], px[2])
    assert redness > 120, f"highlight not clearly red: {tuple(px)}"


def test_locator_box_is_drawn():
    mask = np.zeros((45, 60), dtype=bool)
    mask[10:20, 10:20] = True
    out = _render(mask)
    cyan = (out[:, :, 1] > 200) & (out[:, :, 2] > 200) & (out[:, :, 0] < 90)
    assert cyan.any(), "expected a cyan bounding box around the changed area"


def test_preview_handles_empty_mask():
    # No changed pixels at all must not crash the bounding-box step.
    out = _render(np.zeros((45, 60), dtype=bool))
    assert out.shape[2] == 3


def test_history_click_no_is_separate_from_id():
    # Row ids must stay unique across monitor restarts, while the displayed
    # click number is free to restart at 1.
    h = DetectionHistory(capacity=10)
    a = h.add(index=1, score=0.1, click_no=1)
    b = h.add(index=2, score=0.1, click_no=1)  # restart: click_no repeats
    assert a.index != b.index
    assert a.click_no == b.click_no == 1
    assert h.by_index(2) is b


def test_click_no_defaults_to_index():
    det = DetectionHistory().add(index=7, score=0.1)
    assert det.click_no == 7


def test_beeper_never_raises_without_audio():
    b = Beeper(None)
    b.play()  # must not raise even when nothing can play sound
    assert b.backend in ("canberra-gtk-play", "paplay", "pw-play", "ffplay",
                         "aplay", "tk-bell", "none")
