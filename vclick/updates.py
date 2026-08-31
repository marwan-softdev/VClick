"""Check whether a newer VClick version has been published.

Kept dependency-free (stdlib ``urllib`` only, no import-time network calls)
and the actual HTTP fetch is an injectable parameter -- the same shape as
:class:`~vclick.monitor.Monitor`'s injectable ``Clicker`` -- so it can
be exercised in tests without touching the network.

This compares the installed :data:`vclick.__version__` against the tag of
the most recently published GitHub release. Releases are only ever cut on
an actual version bump (see .github/workflows/cut-stable-release.yml), so
"no newer release" and "no newer version" are the same thing -- unlike the
old per-push rolling "*-latest" releases this replaced, there's no build
timestamp to compare, just semantic versions.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from . import __version__, build_info

REPO = "marwan-softdev/VClick"

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")

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


def _parse_version(tag) -> Optional[Tuple[int, int, int]]:
    if not isinstance(tag, str):
        return None
    match = _VERSION_RE.match(tag)
    return tuple(int(part) for part in match.groups()) if match else None  # type: ignore[return-value]


def check_for_update(fetch: Fetcher = _default_fetch) -> UpdateCheckResult:
    """Compare the installed version against the latest published release."""
    if build_info.BUILD_CHANNEL is None:
        return UpdateCheckResult("not_applicable", "Update checks aren't available for this build.")

    current = _parse_version(__version__)
    if current is None:
        return UpdateCheckResult("error", f"Couldn't parse this build's own version {__version__!r}.")

    try:
        data = json.loads(fetch(f"https://api.github.com/repos/{REPO}/releases"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return UpdateCheckResult("error", f"Couldn't check for updates: {exc}")

    if not isinstance(data, list) or not data:
        return UpdateCheckResult("error", "Couldn't find a published release.")

    latest = data[0] if isinstance(data[0], dict) else {}
    release_url = latest.get("html_url")
    published = _parse_version(latest.get("tag_name"))
    if published is None:
        return UpdateCheckResult("error", "Couldn't read the published release's version.", release_url)

    if published > current:
        return UpdateCheckResult("update_available", "A newer version is available.", release_url)
    return UpdateCheckResult("up_to_date", "You're up to date.", release_url)
