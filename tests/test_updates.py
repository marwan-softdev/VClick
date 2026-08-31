"""Tests for the update-availability check (headless, no real network).

Mirrors test_monitor.py's approach: the real logic runs unmodified, only the
network boundary (the injected ``fetch`` callable) is faked.
"""

import json
import urllib.error

from vclick import build_info, updates


def _release(tag, html_url="https://example.invalid/release"):
    return {"tag_name": tag, "html_url": html_url}


def _fetch_returning(payload):
    def fetch(url):
        return json.dumps(payload).encode("utf-8")

    return fetch


def _fetch_raising(exc):
    def fetch(url):
        raise exc

    return fetch


def test_not_applicable_when_unstamped(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", None)
    result = updates.check_for_update(fetch=_fetch_returning([]))
    assert result.status == "not_applicable"


def test_fetch_failure_is_graceful(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    result = updates.check_for_update(fetch=_fetch_raising(urllib.error.URLError("offline")))
    assert result.status == "error"
    assert "offline" in result.message


def test_update_available_when_latest_release_is_newer(monkeypatch):
    monkeypatch.setattr(updates, "__version__", "0.1.0")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    payload = [_release("v0.2.0", "https://github.com/marwan-softdev/VClick/releases/tag/v0.2.0")]
    result = updates.check_for_update(fetch=_fetch_returning(payload))
    assert result.status == "update_available"
    assert result.release_url == payload[0]["html_url"]


def test_up_to_date_when_latest_release_matches(monkeypatch):
    monkeypatch.setattr(updates, "__version__", "0.1.0")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    payload = [_release("v0.1.0")]
    result = updates.check_for_update(fetch=_fetch_returning(payload))
    assert result.status == "up_to_date"


def test_up_to_date_when_running_ahead_of_the_latest_release(monkeypatch):
    """An unreleased commit on main is never reported as needing an update."""
    monkeypatch.setattr(updates, "__version__", "0.2.0")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    payload = [_release("v0.1.0")]
    result = updates.check_for_update(fetch=_fetch_returning(payload))
    assert result.status == "up_to_date"


def test_beta_releases_compare_the_same_as_any_other(monkeypatch):
    """Version comparison doesn't care whether a release is marked prerelease."""
    monkeypatch.setattr(updates, "__version__", "0.1.0")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "linux-packages")
    payload = [{**_release("v0.1.1"), "prerelease": True}]
    result = updates.check_for_update(fetch=_fetch_returning(payload))
    assert result.status == "update_available"


def test_empty_release_list_is_graceful(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    result = updates.check_for_update(fetch=_fetch_returning([]))
    assert result.status == "error"


def test_unparseable_release_tag_is_graceful(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    result = updates.check_for_update(fetch=_fetch_returning([_release("not-a-version", "u")]))
    assert result.status == "error"
    # The release page is still worth offering even when the tag is unreadable.
    assert result.release_url == "u"


def test_malformed_json_response_is_graceful(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    result = updates.check_for_update(fetch=lambda url: b"not json")
    assert result.status == "error"


def test_non_list_response_is_graceful(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    result = updates.check_for_update(fetch=_fetch_returning({"message": "Not Found"}))
    assert result.status == "error"


def test_parse_version_accepts_leading_v():
    assert updates._parse_version("v1.2.3") == (1, 2, 3)
    assert updates._parse_version("1.2.3") == (1, 2, 3)


def test_parse_version_ignores_trailing_suffix():
    assert updates._parse_version("v0.1.0-beta") == (0, 1, 0)


def test_parse_version_rejects_garbage():
    assert updates._parse_version("not a version") is None
    assert updates._parse_version(None) is None
    assert updates._parse_version("") is None
