"""Tests for the update-availability check (headless, no real network).

Mirrors test_monitor.py's approach: the real logic runs unmodified, only the
network boundary (the injected ``fetch`` callable) is faked.
"""

import json
import urllib.error

from vclick import build_info, updates


def _fetch_returning(payload):
    def fetch(url):
        return json.dumps(payload).encode("utf-8")

    return fetch


def _fetch_raising(exc):
    def fetch(url):
        raise exc

    return fetch


def test_not_applicable_when_unstamped(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", None)
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", None)
    result = updates.check_for_update(fetch=_fetch_returning({}))
    assert result.status == "not_applicable"


def test_not_applicable_for_unknown_channel(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "some-future-channel")
    result = updates.check_for_update(fetch=_fetch_returning({}))
    assert result.status == "not_applicable"


def test_fetch_failure_is_graceful(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "windows-exe")
    result = updates.check_for_update(fetch=_fetch_raising(urllib.error.URLError("offline")))
    assert result.status == "error"
    assert "offline" in result.message


def test_update_available_when_asset_is_newer(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "windows-exe")
    payload = {
        "html_url": "https://github.com/marwan-softdev/VClick/releases/tag/windows-exe-latest-screen-change-q8eylj",
        "published_at": "2026-01-01T00:00:00Z",
        "assets": [{"updated_at": "2026-06-15T12:00:00Z"}],
    }
    result = updates.check_for_update(fetch=_fetch_returning(payload))
    assert result.status == "update_available"
    assert result.release_url == payload["html_url"]


def test_up_to_date_when_asset_is_older(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-06-15T12:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "windows-exe")
    payload = {
        "html_url": "https://example.invalid/release",
        "assets": [{"updated_at": "2026-01-01T00:00:00Z"}],
    }
    result = updates.check_for_update(fetch=_fetch_returning(payload))
    assert result.status == "up_to_date"


def test_up_to_date_when_asset_timestamp_equals_build_time(monkeypatch):
    stamp = "2026-06-15T12:00:00+00:00"
    monkeypatch.setattr(build_info, "BUILD_TIME", stamp)
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "source-packages")
    payload = {"assets": [{"updated_at": "2026-06-15T12:00:00Z"}]}
    result = updates.check_for_update(fetch=_fetch_returning(payload))
    assert result.status == "up_to_date"


def test_missing_timestamps_in_response_is_graceful(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    result = updates.check_for_update(fetch=_fetch_returning({"assets": []}))
    assert result.status == "error"


def test_malformed_json_response_is_graceful(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    result = updates.check_for_update(fetch=lambda url: b"not json")
    assert result.status == "error"


def test_parse_timestamp_accepts_trailing_z():
    # GitHub's API timestamps always end in "Z"; fromisoformat() only accepts
    # that natively on Python 3.11+, so this must be handled by hand.
    dt = updates._parse_timestamp("2026-06-15T12:00:00Z")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 6 and dt.day == 15


def test_parse_timestamp_rejects_garbage():
    assert updates._parse_timestamp("not a date") is None
    assert updates._parse_timestamp(None) is None
    assert updates._parse_timestamp("") is None


def test_falls_back_to_published_at_when_no_assets(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "source-packages")
    payload = {"published_at": "2026-06-15T12:00:00Z", "assets": []}
    result = updates.check_for_update(fetch=_fetch_returning(payload))
    assert result.status == "update_available"
