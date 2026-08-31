from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Event:
    timestamp: datetime
    kind: str
    message: str
    raw_line: str


@dataclass
class Session:
    peer: str
    start: datetime
    end: Optional[datetime] = None
    result: str = "UNKNOWN"
    events: list[Event] = field(default_factory=list)

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.end is None:
            return None
        return max(0.0, (self.end - self.start).total_seconds())
