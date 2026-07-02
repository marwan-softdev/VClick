"""Screen capture helpers.

Capture is done with ``mss`` which is fast and dependency-light.  The only
CPU-relevant work here is turning a captured frame into a small grayscale array
that the detector can diff cheaply, so that logic lives in :func:`to_gray` and
is unit-tested directly (no screen required).
"""

from __future__ import annotations

from typing import Tuple

import numpy as np


def to_gray(raw: bytes, width: int, height: int, downscale_max: int) -> np.ndarray:
    """Convert a raw BGRA frame into a small grayscale ``int16`` array.

    Parameters
    ----------
    raw:
        The raw BGRA bytes from ``mss`` (``ScreenShot.raw``), length
        ``width * height * 4``.
    width, height:
        Dimensions of the captured frame in pixels.
    downscale_max:
        The longest edge the result is shrunk to.  Down-sampling with plain
        array striding keeps this O(output pixels) and dramatically lowers the
        cost of every subsequent diff — the single biggest CPU win for long
        running sessions.

    Returns
    -------
    np.ndarray
        2-D ``int16`` grayscale image (rows × cols).  ``int16`` is chosen so a
        later ``a - b`` cannot overflow like ``uint8`` would.
    """
    arr = np.frombuffer(raw, dtype=np.uint8)
    arr = arr.reshape(height, width, 4)

    step = max(1, int(max(width, height) / max(1, downscale_max)))
    # Stride-based down-sample + drop the alpha channel in one view.
    small = arr[::step, ::step, :3]

    # Mean of B, G, R is plenty for change detection and avoids per-channel
    # float weights.  Accumulate straight into int16 (max sum 765 fits) so the
    # result is a compact, overflow-safe array without an extra astype copy.
    gray = small.sum(axis=2, dtype=np.int16) // 3
    return gray


def capture_size(width: int, height: int, downscale_max: int) -> Tuple[int, int]:
    """Return the (rows, cols) that :func:`to_gray` will produce.  For tests."""
    step = max(1, int(max(width, height) / max(1, downscale_max)))
    rows = len(range(0, height, step))
    cols = len(range(0, width, step))
    return rows, cols


def get_virtual_geometry() -> dict:
    """Return the bounding box covering all monitors: ``{left, top, width, height}``.

    Imported lazily so this module stays importable without a display.
    """
    import mss  # noqa: WPS433 (lazy import on purpose)

    with mss.mss() as sct:
        m = sct.monitors[0]  # index 0 is the union of every monitor
        return {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}
