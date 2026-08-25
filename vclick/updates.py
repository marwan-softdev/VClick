"""Check whether a newer VClick build has been published.

Kept dependency-free (stdlib ``urllib`` only, no import-time network calls)
and the actual HTTP fetch is an injectable parameter -- the same shape as
:class:`~vclick.monitor.Monitor`'s injectable ``Clicker`` -- so it can
be exercised in tests without touching the network.

There is no meaningful version number to compare (``__version__`` has never
changed), so this compares this build's stamped time
(:data:`vclick.build_info.BUILD_TIME`) against the freshness of the
matching GitHub release's assets, fetched from the GitHub REST API. The
release tags are fixed/rolling strings whose *git ref* is not reliable
(re-tagged in place, and can point to a stale commit) -- so only the API's
``assets[].updated_at`` / ``published_at`` / ``html_url`` fields are used,
never the tag ref itself.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from . import build_info

REPO = "marwan-softdev/VClick"
_CHANNEL_TAGS = {
    "appimage": "appimage-latest-screen-change-q8eylj",
    "windows-exe": "windows-exe-latest-screen-change-q8eylj",
    "source-packages": "source-packages-latest-screen-change-q8eylj",
}

Fetcher = Callable[[str], bytes]


def _default_fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "VClick-update-check",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - fixed https:// API URL
        return resp.read()


@dataclass
class UpdateCheckResult:
    """Outcome of one update check."""

    status: str  # "not_applicable" | "up_to_date" | "update_available" | "error"
    message: str
    release_url: Optional[str] = None


def _parse_timestamp(ts) -> Optional[datetime]:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        # fromisoformat() only accepts a trailing "Z" from Python 3.11+, but
        # a source-package install can run under whatever Python the user
        # has (>=3.8 per pyproject.toml) -- normalise by hand so this works
        # on every supported version, not just CI's.
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def check_for_update(fetch: Fetcher = _default_fetch) -> UpdateCheckResult:
    """Compare this build's stamp against the matching release's freshness."""
    build_time = _parse_timestamp(build_info.BUILD_TIME)
    tag = _CHANNEL_TAGS.get(build_info.BUILD_CHANNEL)
    if build_time is None or tag is None:
        return UpdateCheckResult("not_applicable", "Update checks aren't available for this build.")

    try:
        data = json.loads(fetch(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return UpdateCheckResult("error", f"Couldn't check for updates: {exc}")

    stamps = [
        t
        for t in (
            _parse_timestamp(data.get("published_at")),
            *(_parse_timestamp(a.get("updated_at")) for a in data.get("assets") or []),
        )
        if t is not None
    ]
    if not stamps:
        return UpdateCheckResult("error", "Couldn't read the release's build time.")

    release_url = data.get("html_url")
    if max(stamps) > build_time:
        return UpdateCheckResult("update_available", "A newer build is available.", release_url)
    return UpdateCheckResult("up_to_date", "You're up to date.", release_url)
