"""Tests for the bounded detection history behind the Why/Log view."""

import time

from screenwatch.config import Config
from screenwatch.history import Detection, DetectionHistory


def test_add_and_retrieve():
    h = DetectionHistory(capacity=10)
    det = h.add(index=1, score=0.25, preview="abc")
    assert len(h) == 1
    assert h.by_index(1) is det
    assert det.has_image is True
    assert det.score_str == "25.00%"


def test_detection_without_image():
    h = DetectionHistory()
    det = h.add(index=1, score=0.1, preview=None)
    assert det.has_image is False


def test_time_str_formats_from_timestamp():
    ts = time.mktime(time.strptime("2026-01-02 13:45:07", "%Y-%m-%d %H:%M:%S"))
    det = Detection(index=1, score=0.5, timestamp=ts)
    assert det.time_str == "13:45:07"


def test_history_is_bounded_and_evicts_oldest():
    h = DetectionHistory(capacity=3)
    for i in range(1, 6):
        h.add(index=i, score=0.1, preview="x")
    assert len(h) == 3
    # The three most recent survive; the oldest two are gone.
    assert [d.index for d in h] == [3, 4, 5]
    assert h.by_index(1) is None
    assert h.by_index(5) is not None


def test_latest_returns_most_recent():
    h = DetectionHistory()
    assert h.latest is None
    h.add(index=1, score=0.1)
    h.add(index=2, score=0.2)
    assert h.latest.index == 2


def test_set_capacity_shrinks_keeping_newest():
    h = DetectionHistory(capacity=10)
    for i in range(1, 6):
        h.add(index=i, score=0.1)
    h.set_capacity(2)
    assert len(h) == 2
    assert [d.index for d in h] == [4, 5]
    # Newly added entries still respect the smaller cap.
    h.add(index=6, score=0.1)
    assert [d.index for d in h] == [5, 6]


def test_set_capacity_grows():
    h = DetectionHistory(capacity=2)
    h.add(index=1, score=0.1)
    h.add(index=2, score=0.1)
    h.set_capacity(5)
    h.add(index=3, score=0.1)
    assert [d.index for d in h] == [1, 2, 3]


def test_clear_empties_history():
    h = DetectionHistory()
    h.add(index=1, score=0.1)
    h.clear()
    assert len(h) == 0
    assert h.latest is None


def test_capacity_is_at_least_one():
    h = DetectionHistory(capacity=0)
    assert h.capacity >= 1


def test_config_log_history_defaults_and_clamps():
    assert Config().log_history == 30
    assert Config(log_history=1).clamp().log_history == 5
    assert Config(log_history=9999).clamp().log_history == 200


def test_config_log_history_roundtrips():
    restored = Config.from_dict(Config(log_history=75).to_dict())
    assert restored.log_history == 75
