#!/usr/bin/env python3
"""Stamp vclick/build_info.py with this CI run's package channel.

Run by each build workflow right after checkout, before that channel's build
script runs, so the finished artifact records which packaging format it came
from. vclick.updates.check_for_update() uses this only to tell a packaged
build (channel set) from a dev checkout (channel None, "not applicable") --
update checks otherwise compare vclick.__version__ against the latest
release's tag, not anything build-specific.

Usage: python packaging/stamp_build_info.py <channel>
"""

from __future__ import annotations

import sys
from pathlib import Path

TEMPLATE = '''"""Build stamp, overwritten at CI package time by packaging/stamp_build_info.py.

``None`` means "not a stamped package build" -- a dev checkout, a
`pip install -e .`, or a pre-feature package. :mod:`vclick.updates`
treats that as "not applicable", never as an error.
"""

from __future__ import annotations

BUILD_CHANNEL: str | None = {channel!r}
'''


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: stamp_build_info.py <channel>", file=sys.stderr)
        return 2
    channel = argv[1]
    target = Path(__file__).resolve().parent.parent / "vclick" / "build_info.py"
    target.write_text(TEMPLATE.format(channel=channel), encoding="utf-8")
    print(f"Stamped {target}: BUILD_CHANNEL={channel}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
