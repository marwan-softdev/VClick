#!/usr/bin/env python3
"""Stamp vclick/build_info.py with this CI run's build time + channel.

Run by each release workflow right after checkout, before that channel's
build script runs, so the finished artifact bundles a real BUILD_TIME the
running app can compare against the matching GitHub release to detect
"is there a newer build" (vclick.updates.check_for_update).

The same timestamp is also emitted as the "build-time" step output, so the
workflow can write it into the release body as the marker that check reads.
Both sides of the comparison must be this one value: comparing the stamp
against GitHub's own asset-upload times instead is what made every fresh
download report "update available" (see vclick/updates.py).

Usage: python packaging/stamp_build_info.py <channel>
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

TEMPLATE = '''"""Build stamp, overwritten at CI package time by packaging/stamp_build_info.py.

``None``/``None`` means "not a stamped package build" -- a dev checkout, a
`pip install -e .`, or a pre-feature package. :mod:`vclick.updates`
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
    # Timezone-aware, not utcnow() -- vclick.updates compares this
    # against timezone-aware timestamps parsed from GitHub's API and raises
    # on a naive/aware mismatch.
    build_time = datetime.now(timezone.utc).isoformat()
    target = Path(__file__).resolve().parent.parent / "vclick" / "build_info.py"
    target.write_text(TEMPLATE.format(build_time=build_time, channel=channel), encoding="utf-8")
    print(f"Stamped {target}: BUILD_TIME={build_time} BUILD_CHANNEL={channel}")

    # Hand the exact same string to the workflow so it can publish it in the
    # release body. Absent outside CI, where there is no file to append to.
    step_output = os.environ.get("GITHUB_OUTPUT")
    if step_output:
        with open(step_output, "a", encoding="utf-8") as fh:
            fh.write(f"build-time={build_time}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
