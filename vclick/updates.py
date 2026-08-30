"""Check whether a newer VClick build has been published.

Kept dependency-free (stdlib ``urllib`` only, no import-time network calls)
and the actual HTTP fetch is an injectable parameter -- the same shape as
:class:`~vclick.monitor.Monitor`'s injectable ``Clicker`` -- so it can
be exercised in tests without touching the network.

There is no meaningful version number to compare (``__version__`` changes
only when a stable release is cut, while these rolling channels rebuild on
every push), so this compares this build's stamped time
(:data:`vclick.build_info.BUILD_TIME`) against the *stamped time of the
build currently published* on the matching channel, which each release
workflow writes into its release body as a machine-readable marker (see
``_BUILD_MARKER``).

Comparing stamp-to-stamp is the whole point: the two numbers come from the
same clock at the same point in each build, so the freshest download reads
as exactly up to date. The obvious-looking alternative -- comparing against
the release's ``published_at``/``assets[].updated_at`` -- is structurally
broken, and was the bug this replaced: the stamp is written right after
checkout but the assets are uploaded at the *end* of the same run, so a
build's own assets are always ~1-2 minutes "newer" than the build inside
them and every fresh download reported "update available" forever.

The release tags are fixed/rolling strings whose *git ref* is not reliable
(re-tagged in place, and can point to a stale commit), so the tag ref is
never used either.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from . import build_info

REPO = "marwan-softdev/VClick"
_CHANNEL_TAGS = {
    "appimage": "appimage-latest",
    "linux-packages": "linux-packages-latest",
    "source-packages": "source-packages-latest",
}

# Written into each rolling release's body by the publishing workflow, from
# the very same value packaging/stamp_build_info.py baked into the artifact.
# An HTML comment so it carries no weight in the rendered release notes.
_BUILD_MARKER = re.compile(r"<!--\s*vclick-build-time:\s*(\S+?)\s*-->")

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


def _published_build_time(body) -> Optional[datetime]:
    """Pull the published build's stamp out of a release body, if present."""
    if not isinstance(body, str):
        return None
    match = _BUILD_MARKER.search(body)
    return _parse_timestamp(match.group(1)) if match else None


def check_for_update(fetch: Fetcher = _default_fetch) -> UpdateCheckResult:
    """Compare this build's stamp against the published build's stamp."""
    build_time = _parse_timestamp(build_info.BUILD_TIME)
    tag = _CHANNEL_TAGS.get(build_info.BUILD_CHANNEL)
    if build_time is None or tag is None:
        return UpdateCheckResult("not_applicable", "Update checks aren't available for this build.")

    try:
        data = json.loads(fetch(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return UpdateCheckResult("error", f"Couldn't check for updates: {exc}")

    release_url = data.get("html_url") if isinstance(data, dict) else None
    published = _published_build_time(data.get("body") if isinstance(data, dict) else None)
    if published is None:
        # A release published before this marker existed, or by something
        # other than the workflows. Reporting "couldn't tell" beats guessing
        # from the upload timestamps, which is what produced false
        # "update available" on every single fresh download.
        return UpdateCheckResult("error", "Couldn't read the published build's time.", release_url)

    if published > build_time:
        return UpdateCheckResult("update_available", "A newer build is available.", release_url)
    return UpdateCheckResult("up_to_date", "You're up to date.", release_url)
