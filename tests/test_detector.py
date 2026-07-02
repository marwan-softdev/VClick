"""Tests for the change detector — the CPU-critical core, fully headless."""

import numpy as np

from screenwatch.detector import ChangeDetector, DetectionResult, sensitivity_to_area


def _frame(value, shape=(50, 50)):
    return np.full(shape, value, dtype=np.int16)


def test_first_frame_is_never_a_change():
    det = ChangeDetector(sensitivity=90)
    res = det.process(_frame(100))
    assert isinstance(res, DetectionResult)
    assert res.changed is False
    assert res.score == 0.0


def test_identical_frames_do_not_trigger():
    det = ChangeDetector(sensitivity=90)
    det.process(_frame(100))
    res = det.process(_frame(100))
    assert res.changed is False
    assert res.score == 0.0


def test_full_frame_change_triggers():
    det = ChangeDetector(sensitivity=50, pixel_threshold=25)
    det.process(_frame(0))
    res = det.process(_frame(255))  # every pixel flips hard
    assert res.changed is True
    assert res.score == 1.0


def test_noise_below_pixel_threshold_is_ignored():
    det = ChangeDetector(sensitivity=100, pixel_threshold=25)
    det.process(_frame(100))
    res = det.process(_frame(110))  # delta of 10 < threshold 25
    assert res.changed is False
    assert res.score == 0.0


def test_small_change_needs_high_sensitivity():
    # Change a single pixel out of 2500 (0.04% of the area).
    base = _frame(0)
    changed = base.copy()
    changed[0, 0] = 255

    low = ChangeDetector(sensitivity=1, pixel_threshold=10)
    low.process(base.copy())
    assert low.process(changed.copy()).changed is False

    high = ChangeDetector(sensitivity=100, pixel_threshold=10)
    high.process(base.copy())
    assert high.process(changed.copy()).changed is True


def test_previous_mode_tracks_frame_to_frame():
    det = ChangeDetector(sensitivity=50, compare_mode="previous")
    det.process(_frame(0))
    assert det.process(_frame(255)).changed is True
    # Now the reference is 255; another 255 frame is no longer a change.
    assert det.process(_frame(255)).changed is False


def test_baseline_mode_keeps_reference_fixed():
    det = ChangeDetector(sensitivity=50, compare_mode="baseline")
    det.process(_frame(0))  # baseline captured
    assert det.process(_frame(255)).changed is True
    # Still compared to the 0 baseline, so 255 keeps triggering.
    assert det.process(_frame(255)).changed is True


def test_reset_forgets_reference():
    det = ChangeDetector(sensitivity=90)
    det.process(_frame(0))
    det.reset()
    # After reset the next frame becomes the new reference (no change reported).
    assert det.process(_frame(255)).changed is False


def test_shape_change_is_handled_gracefully():
    det = ChangeDetector(sensitivity=90)
    det.process(_frame(0, shape=(50, 50)))
    res = det.process(_frame(0, shape=(30, 30)))  # region re-selected
    assert res.changed is False


def test_sensitivity_mapping_is_monotonic():
    areas = [sensitivity_to_area(s) for s in range(1, 101)]
    # More sensitivity => smaller required area, strictly decreasing.
    assert all(a > b for a, b in zip(areas, areas[1:]))
    assert areas[0] > 0.5   # insensitive end needs a big change
    assert areas[-1] < 0.01  # sensitive end reacts to tiny changes
