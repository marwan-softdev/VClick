"""Tests for the capture/downsample conversion (no screen required)."""

import numpy as np

from vclick.capture import capture_size, to_color_samples


def _bgra(width, height, b, g, r, a=255):
    px = np.array([b, g, r, a], dtype=np.uint8)
    return np.tile(px, width * height).tobytes()


def test_shape_matches_capture_size():
    w, h, dmax = 200, 100, 50
    raw = _bgra(w, h, 10, 20, 30)
    frame = to_color_samples(raw, w, h, dmax)
    assert frame.shape[:2] == capture_size(w, h, dmax)
    assert frame.shape[2] == 3
    assert frame.dtype == np.int16


def test_no_downscale_when_region_is_small():
    w, h = 40, 30
    raw = _bgra(w, h, 0, 0, 0)
    frame = to_color_samples(raw, w, h, downscale_max=120)
    assert frame.shape == (h, w, 3)  # step == 1


def test_channels_are_preserved_not_averaged():
    # Earlier versions collapsed B/G/R to a single mean value, which is
    # exactly what let a hue change with similar brightness go undetected.
    w, h = 10, 10
    raw = _bgra(w, h, 30, 60, 90)
    frame = to_color_samples(raw, w, h, downscale_max=120)
    assert np.all(frame[:, :, 0] == 30)  # B
    assert np.all(frame[:, :, 1] == 60)  # G
    assert np.all(frame[:, :, 2] == 90)  # R


def test_downscale_reduces_dimensions():
    w, h, dmax = 1000, 500, 100
    raw = _bgra(w, h, 0, 0, 0)
    frame = to_color_samples(raw, w, h, dmax)
    rows, cols = frame.shape[:2]
    assert max(rows, cols) <= dmax + 1
    assert rows < h and cols < w
