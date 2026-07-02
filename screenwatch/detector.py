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
    ) -> None:
        self.pixel_threshold = int(pixel_threshold)
        self.compare_mode = compare_mode
        self.area_threshold = sensitivity_to_area(sensitivity)
        self._reference: Optional[np.ndarray] = None

    def reset(self) -> None:
        """Forget the reference frame (e.g. after a click or when restarting)."""
        self._reference = None

    def update_settings(self, sensitivity: int, pixel_threshold: int, compare_mode: str) -> None:
        """Apply live GUI changes without dropping the reference frame."""
        self.area_threshold = sensitivity_to_area(sensitivity)
        self.pixel_threshold = int(pixel_threshold)
        self.compare_mode = compare_mode

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
        changed_pixels = np.count_nonzero(diff > self.pixel_threshold)
        score = changed_pixels / diff.size if diff.size else 0.0
        changed = bool(score >= self.area_threshold)

        if self.compare_mode == "previous":
            # Always advance the reference so we track frame-to-frame motion.
            self._reference = frame
        # In "baseline" mode the reference stays fixed until reset().

        return DetectionResult(changed=changed, score=float(score))
