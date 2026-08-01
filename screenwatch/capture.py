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


def build_change_preview(
    raw: bytes,
    width: int,
    height: int,
    mask: "np.ndarray",
    out_max: int = 240,
) -> str:
    """Render a "why it detected" image and return it as a base64 PNG string.

    The captured region is shown in colour with the pixels that changed tinted
    red, so the user can see exactly *where* and *how much* changed.  Returns a
    base64 string that Tk's ``PhotoImage(data=...)`` can display directly (no
    ImageTk needed).  Only called when a change is actually detected, so its
    cost never touches the steady-state loop.
    """
    import base64
    import io

    from PIL import Image

    from PIL import ImageDraw

    bgra = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)
    rgb = bgra[:, :, [2, 1, 0]].astype(np.float32)  # BGR -> RGB

    # The mask is at the detector's downscaled resolution; blow it up to the
    # full region with nearest-neighbour so blocks line up with what changed.
    mask_img = Image.fromarray((mask.astype(np.uint8) * 255), mode="L").resize(
        (width, height), resample=Image.NEAREST
    )
    full = np.asarray(mask_img) > 127
    m = full[:, :, None]

    # Unchanged pixels are converted to a DARK GREY-SCALE version of the
    # original.  Desaturating them completely is what makes the highlight
    # unmistakable: a red tint on top of already-warm content (an orange
    # sprite, a red button) is nearly invisible, but red against grey is not.
    luma = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2])
    grey = np.repeat((luma * 0.45)[:, :, None], 3, axis=2)

    # Changed pixels keep a little of their own luminance for shape, but are
    # pushed hard towards a saturated red.
    hot = np.empty_like(rgb)
    hot[:, :, 0] = np.clip(150.0 + 0.42 * luma, 0, 255)   # strong red
    hot[:, :, 1] = np.clip(0.22 * luma, 0, 255)           # little green
    hot[:, :, 2] = np.clip(0.22 * luma, 0, 255)           # little blue

    out = np.where(m, hot, grey)
    img = Image.fromarray(out.clip(0, 255).astype(np.uint8), mode="RGB")

    # Outline the changed area so small changes are easy to spot at a glance.
    rows = np.flatnonzero(full.any(axis=1))
    cols = np.flatnonzero(full.any(axis=0))
    if rows.size and cols.size:
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])],
            outline=(0, 255, 255), width=max(1, min(width, height) // 100),
        )

    img.thumbnail((out_max, out_max), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def get_virtual_geometry() -> dict:
    """Return the bounding box covering all monitors: ``{left, top, width, height}``.

    Imported lazily so this module stays importable without a display.
    """
    import mss  # noqa: WPS433 (lazy import on purpose)

    with mss.mss() as sct:
        m = sct.monitors[0]  # index 0 is the union of every monitor
        return {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}
