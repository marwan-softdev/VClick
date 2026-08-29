"""Build stamp, overwritten at CI package time by packaging/stamp_build_info.py.

``None``/``None`` means "not a stamped package build" -- a dev checkout, a
`pip install -e .`, or a pre-feature package. :mod:`vclick.updates`
treats that as "not applicable", never as an error.
"""

from __future__ import annotations

BUILD_TIME: str | None = None
BUILD_CHANNEL: str | None = None  # "appimage" | "linux-packages" | "source-packages"
