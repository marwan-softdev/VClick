"""Tests for the update-availability check (headless, no real network).

Mirrors test_monitor.py's approach: the real logic runs unmodified, only the
network boundary (the injected ``fetch`` callable) is faked.
"""

import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

from vclick import build_info, updates


def _body(build_time):
    """A release body shaped like the ones the publishing workflows write."""
    return (
        "Automatically built from commit abc123 by the\n"
        "`Build AppImage` workflow.\n"
        "\n"
        f"<!-- vclick-build-time: {build_time} -->\n"
    )


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
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    result = updates.check_for_update(fetch=_fetch_raising(urllib.error.URLError("offline")))
    assert result.status == "error"
    assert "offline" in result.message


def test_update_available_when_published_build_is_newer(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    payload = {
        "html_url": "https://github.com/marwan-softdev/VClick/releases/tag/appimage-latest",
        "body": _body("2026-06-15T12:00:00+00:00"),
    }
    result = updates.check_for_update(fetch=_fetch_returning(payload))
    assert result.status == "update_available"
    assert result.release_url == payload["html_url"]


def test_up_to_date_when_published_build_is_older(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-06-15T12:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    payload = {
        "html_url": "https://example.invalid/release",
        "body": _body("2026-01-01T00:00:00+00:00"),
    }
    result = updates.check_for_update(fetch=_fetch_returning(payload))
    assert result.status == "up_to_date"


def test_up_to_date_when_running_the_published_build(monkeypatch):
    """The freshest possible download must read as up to date, not stale.

    Regression test for the bug where this compared the build's stamp (written
    right after checkout) against the release's *asset upload* times (written
    at the end of that same run). Those are always ~1-2 minutes apart, so a
    just-downloaded build reported "update available" forever. The numbers
    below are the real ones from the run that shipped it: stamped 06:12:42,
    assets uploaded 06:14:16.
    """
    stamp = "2026-08-30T06:12:42.123456+00:00"
    monkeypatch.setattr(build_info, "BUILD_TIME", stamp)
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "linux-packages")
    payload = {
        "html_url": "https://example.invalid/release",
        "body": _body(stamp),
        # Present, and deliberately newer -- nothing may key off these.
        "published_at": "2026-08-30T06:14:16Z",
        "assets": [
            {"updated_at": "2026-08-30T06:14:16Z"},
            {"updated_at": "2026-08-30T06:14:16Z"},
        ],
    }
    result = updates.check_for_update(fetch=_fetch_returning(payload))
    assert result.status == "up_to_date"


def test_asset_timestamps_alone_never_signal_an_update(monkeypatch):
    """Upload times must not stand in for the marker when it's absent."""
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    payload = {
        "body": "Automatically built from commit abc123. No marker here.",
        "published_at": "2026-06-15T12:00:00Z",
        "assets": [{"updated_at": "2026-06-15T12:00:00Z"}],
    }
    result = updates.check_for_update(fetch=_fetch_returning(payload))
    assert result.status == "error"


def test_missing_body_is_graceful(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    result = updates.check_for_update(fetch=_fetch_returning({"html_url": "u"}))
    assert result.status == "error"
    # The release page is still worth offering even when the stamp is unreadable.
    assert result.release_url == "u"


def test_unparseable_marker_is_graceful(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    result = updates.check_for_update(fetch=_fetch_returning({"body": _body("not-a-date")}))
    assert result.status == "error"


def test_malformed_json_response_is_graceful(monkeypatch):
    monkeypatch.setattr(build_info, "BUILD_TIME", "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(build_info, "BUILD_CHANNEL", "appimage")
    result = updates.check_for_update(fetch=lambda url: b"not json")
    assert result.status == "error"


def test_published_build_time_reads_the_marker():
    assert updates._published_build_time(_body("2026-06-15T12:00:00+00:00")) is not None
    # Tolerant of the spacing GitHub's markdown round-trip may leave behind.
    assert updates._published_build_time("<!--vclick-build-time:2026-06-15T12:00:00Z-->") is not None
    assert updates._published_build_time("no marker at all") is None
    assert updates._published_build_time(None) is None


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


def test_stamp_script_publishes_the_same_time_it_bakes_in(tmp_path):
    """The two halves of the comparison must come from one value.

    The workflow writes the script's ``build-time`` step output into the
    release body; the artifact carries ``BUILD_TIME``. If those two ever
    drift apart, a fresh download starts lying again.
    """
    # The script writes next to itself (../vclick/build_info.py), so run a
    # copy inside tmp_path rather than letting it stamp the real checkout.
    repo = Path(__file__).resolve().parent.parent
    script = tmp_path / "packaging" / "stamp_build_info.py"
    script.parent.mkdir()
    script.write_bytes((repo / "packaging" / "stamp_build_info.py").read_bytes())
    (tmp_path / "vclick").mkdir()

    github_output = tmp_path / "gh_output"
    subprocess.run(
        [sys.executable, str(script), "appimage"],
        check=True,
        env=dict(os.environ, GITHUB_OUTPUT=str(github_output)),
        capture_output=True,
    )

    baked = (tmp_path / "vclick" / "build_info.py").read_text(encoding="utf-8")
    published = github_output.read_text(encoding="utf-8").strip()
    assert published.startswith("build-time=")
    build_time = published[len("build-time=") :]

    assert repr(build_time) in baked, "step output drifted from the baked-in stamp"
    assert updates._parse_timestamp(build_time) is not None
    # And the marker the workflow builds from that output round-trips.
    assert updates._published_build_time(_body(build_time)) == updates._parse_timestamp(build_time)
