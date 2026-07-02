"""Tests for the capture/grayscale conversion (no screen required)."""

import numpy as np

from screenwatch.capture import capture_size, to_gray


def _bgra(width, height, b, g, r, a=255):
    px = np.array([b, g, r, a], dtype=np.uint8)
    return np.tile(px, width * height).tobytes()


def test_to_gray_shape_matches_capture_size():
    w, h, dmax = 200, 100, 50
    raw = _bgra(w, h, 10, 20, 30)
    gray = to_gray(raw, w, h, dmax)
    assert gray.shape == capture_size(w, h, dmax)
    assert gray.dtype == np.int16


def test_no_downscale_when_region_is_small():
    w, h = 40, 30
    raw = _bgra(w, h, 0, 0, 0)
    gray = to_gray(raw, w, h, downscale_max=120)
    assert gray.shape == (h, w)  # step == 1


def test_gray_value_is_channel_mean():
    w, h = 10, 10
    raw = _bgra(w, h, 30, 60, 90)  # mean = 60
    gray = to_gray(raw, w, h, downscale_max=120)
    assert np.all(gray == 60)


def test_downscale_reduces_dimensions():
    w, h, dmax = 1000, 500, 100
    raw = _bgra(w, h, 0, 0, 0)
    gray = to_gray(raw, w, h, dmax)
    rows, cols = gray.shape
    assert max(rows, cols) <= dmax + 1
    assert rows < h and cols < w
