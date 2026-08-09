"""Visual change detection.

The detector receives successive grayscale frames (from :mod:`screenwatch.capture`)
and reports whether the watched region changed enough to warrant a click.

Algorithm (deliberately simple and cheap):

1. Compute the absolute per-pixel difference between the current frame and a
   reference frame.
2. Count the fraction of pixels whose difference exceeds ``pixel_threshold``
   (this ignores small rendering/compression noise).
3. If that fraction meets the area threshold derived from ``sensitivity``,
   report a change.

Two reference strategies are supported:

* ``"previous"`` — compare to the immediately preceding frame (reacts to *any*
  visual change / motion).
* ``"baseline"`` — compare to the first frame captured after start (reacts to a
  *deviation* from a known state).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


def sensitivity_to_area(sensitivity: int) -> float:
    """Map a 1..100 sensitivity slider to a required "changed area" fraction.

    Higher sensitivity → smaller required area → reacts to smaller changes.
    The mapping is exponential so the low end is genuinely coarse (needs a big
    change) and the high end is genuinely fine-grained.

    * sensitivity 1   → ~0.60  (60% of the region must change)
    * sensitivity 50  → ~0.012 (about 1.2%)
    * sensitivity 100 → ~0.0002 (essentially any change)
    """
    sensitivity = max(1, min(100, int(sensitivity)))
    # Interpolate the exponent between two endpoints on a log scale.
    hi = np.log10(0.60)      # at sensitivity = 1
    lo = np.log10(0.0002)    # at sensitivity = 100
    t = (sensitivity - 1) / 99.0
    return float(10 ** (hi + (lo - hi) * t))


@dataclass
class DetectionResult:
    changed: bool
    score: float  # fraction of pixels that changed (0..1)


class ChangeDetector:
    """Stateful frame comparator.  Not thread-safe; use from one thread."""

    def __init__(
        self,
        sensitivity: int = 50,
        pixel_threshold: int = 25,
        compare_mode: str = "previous",
        keep_mask: bool = False,
    ) -> None:
        self.pixel_threshold = int(pixel_threshold)
        self.compare_mode = compare_mode
        self.area_threshold = sensitivity_to_area(sensitivity)
        self.keep_mask = keep_mask
        # When keep_mask is on, this holds the boolean "which pixels changed"
        # array from the most recent comparison, for the GUI's why-view.
        self.last_mask: Optional[np.ndarray] = None
        self._reference: Optional[np.ndarray] = None

    def reset(self) -> None:
        """Forget the reference frame (e.g. after a click or when restarting)."""
        self._reference = None
        self.last_mask = None

    def update_settings(
        self,
        sensitivity: int,
        pixel_threshold: int,
        compare_mode: str,
        keep_mask: Optional[bool] = None,
    ) -> None:
        """Apply live GUI changes without dropping the reference frame."""
        self.area_threshold = sensitivity_to_area(sensitivity)
        self.pixel_threshold = int(pixel_threshold)
        self.compare_mode = compare_mode
        if keep_mask is not None:
            self.keep_mask = keep_mask

    def process(self, frame: np.ndarray) -> DetectionResult:
        """Feed one grayscale frame; return whether it counts as a change."""
        if self._reference is None:
            self._reference = frame
            return DetectionResult(changed=False, score=0.0)

        # Guard against the region changing shape (e.g. re-selected mid-run).
        if frame.shape != self._reference.shape:
            self._reference = frame
            return DetectionResult(changed=False, score=0.0)

        diff = np.abs(frame - self._reference)
        if diff.ndim == 3:
            # Colour frames (rows, cols, channels): use the single biggest
            # channel delta per pixel rather than an average. Averaging masks
            # hue changes with similar overall brightness (a purple button
            # swapping to green, say) — the strongest channel still shows a
            # large delta even when the mean barely moves.
            pixel_diff = diff.max(axis=2)
        else:
            pixel_diff = diff
        mask = pixel_diff > self.pixel_threshold
        changed_pixels = int(np.count_nonzero(mask))
        score = changed_pixels / mask.size if mask.size else 0.0
        changed = bool(score >= self.area_threshold)
        # Only keep the mask when the GUI wants to explain detections; this
        # avoids retaining an extra array on every frame during normal runs.
        self.last_mask = mask if self.keep_mask else None

        if self.compare_mode == "previous":
            # Always advance the reference so we track frame-to-frame motion.
            self._reference = frame
        # In "baseline" mode the reference stays fixed until reset().

        return DetectionResult(changed=changed, score=float(score))
