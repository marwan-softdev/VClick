#!/usr/bin/env python3
"""Stamp screenwatch/build_info.py with this CI run's build time + channel.

Run by each release workflow right after checkout, before that channel's
build script runs, so the finished artifact bundles a real BUILD_TIME the
running app can compare against the matching GitHub release to detect
"is there a newer build" (screenwatch.updates.check_for_update).

Usage: python packaging/stamp_build_info.py <channel>
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

TEMPLATE = '''"""Build stamp, overwritten at CI package time by packaging/stamp_build_info.py.

``None``/``None`` means "not a stamped package build" -- a dev checkout, a
`pip install -e .`, or a pre-feature package. :mod:`screenwatch.updates`
treats that as "not applicable", never as an error.
"""

from __future__ import annotations

BUILD_TIME: str | None = {build_time!r}
BUILD_CHANNEL: str | None = {channel!r}
'''


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: stamp_build_info.py <channel>", file=sys.stderr)
        return 2
    channel = argv[1]
    # Timezone-aware, not utcnow() -- screenwatch.updates compares this
    # against timezone-aware timestamps parsed from GitHub's API and raises
    # on a naive/aware mismatch.
    build_time = datetime.now(timezone.utc).isoformat()
    target = Path(__file__).resolve().parent.parent / "screenwatch" / "build_info.py"
    target.write_text(TEMPLATE.format(build_time=build_time, channel=channel), encoding="utf-8")
    print(f"Stamped {target}: BUILD_TIME={build_time} BUILD_CHANNEL={channel}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
