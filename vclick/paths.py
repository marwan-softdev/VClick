"""Locate bundled data files (the app icon) regardless of how it was launched.

The icon lives inside the package at ``vclick/assets/`` and is declared
as package data in ``pyproject.toml``, so it is found the same way whether
VClick is run from a source checkout, an editable install
(``pip install -e .``, what both installers use), or a regular ``pip install``
into site-packages.
"""

from __future__ import annotations

import os
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))


def _candidates():
    yield os.path.join(_HERE, "assets", "icon.png")
    # Legacy/alternate layout: a top-level assets/ dir next to the package.
    yield os.path.join(os.path.dirname(_HERE), "assets", "icon.png")


def icon_path() -> Optional[str]:
    """Return the absolute path to the app icon PNG, or ``None`` if not found."""
    for path in _candidates():
        if os.path.isfile(path):
            return path
    return None


def icon_ico_path() -> Optional[str]:
    """Return the absolute path to the Windows multi-size .ico, or ``None``."""
    png = icon_path()
    if png is None:
        return None
    ico = os.path.join(os.path.dirname(png), "icon.ico")
    return ico if os.path.isfile(ico) else None
