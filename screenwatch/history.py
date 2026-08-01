"""Detection history — the records behind the "Why / Log" view.

Each time a change triggers a click we keep a small record of *why*: when it
happened, how much of the region changed, and (optionally) a rendered image
highlighting the pixels responsible.

The store is deliberately bounded.  A 4–5 hour session can produce thousands of
detections, and every image costs memory, so :class:`DetectionHistory` keeps
only the most recent ``capacity`` records and drops the oldest automatically.

No GUI or capture dependencies here, so it is fully unit-testable headlessly.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Iterator, List, Optional


@dataclass
class Detection:
    """One "the region changed, so I clicked" event."""

    index: int                      # click number, 1-based
    score: float                    # fraction of the region that changed (0..1)
    timestamp: float = field(default_factory=time.time)
    preview: Optional[str] = None   # base64 PNG explaining the change

    @property
    def has_image(self) -> bool:
        return bool(self.preview)

    @property
    def time_str(self) -> str:
        return time.strftime("%H:%M:%S", time.localtime(self.timestamp))

    @property
    def score_str(self) -> str:
        return f"{self.score * 100:.2f}%"


class DetectionHistory:
    """A bounded, newest-last collection of :class:`Detection` records."""

    def __init__(self, capacity: int = 40) -> None:
        self.capacity = max(1, int(capacity))
        self._items: Deque[Detection] = deque(maxlen=self.capacity)

    def add(self, index: int, score: float, preview: Optional[str] = None,
            timestamp: Optional[float] = None) -> Detection:
        """Record a detection and return it.  Oldest entries are evicted."""
        det = Detection(
            index=index,
            score=score,
            preview=preview,
            timestamp=time.time() if timestamp is None else timestamp,
        )
        self._items.append(det)
        return det

    def by_index(self, index: int) -> Optional[Detection]:
        """Look a record up by its click number, or ``None`` if it aged out."""
        for det in self._items:
            if det.index == index:
                return det
        return None

    @property
    def latest(self) -> Optional[Detection]:
        return self._items[-1] if self._items else None

    def set_capacity(self, capacity: int) -> None:
        """Resize the store, keeping the most recent records."""
        capacity = max(1, int(capacity))
        if capacity == self.capacity:
            return
        self.capacity = capacity
        self._items = deque(self._items, maxlen=capacity)

    def clear(self) -> None:
        self._items.clear()

    def to_list(self) -> List[Detection]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Detection]:
        return iter(self._items)
