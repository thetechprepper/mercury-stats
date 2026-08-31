from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from models import Session


MODE_RE = re.compile(r"\b(DATAC\d+|QAM16C2)\b", re.IGNORECASE)
BYTES_RE = re.compile(r"\b(?P<count>\d+)\s*(?:bytes?|B)\b", re.IGNORECASE)
SETUP_MARKERS = (
    "connected",
    "connection established",
    "arq connected",
    "session established",
)


@dataclass
class SessionMetrics:
    peer: str
    result: str
    duration_seconds: Optional[float]
    setup_seconds: Optional[float]
    bytes_seen: int
    retries: int
    mode_upgrades: int
    mode_downgrades: int
    initial_mode: str | None
    final_mode: str | None
    modes_seen: list[str]


def calculate_metrics(session: Session) -> SessionMetrics:
    retries = 0
    upgrades = 0
    downgrades = 0
    bytes_seen = 0
    modes: list[str] = []
    setup_seconds = None

    for event in session.events:
        lower = event.message.lower()

        if event.kind == "retry":
            retries += 1
        elif event.kind == "mode_upgrade":
            upgrades += 1
        elif event.kind == "mode_downgrade":
            downgrades += 1

        if setup_seconds is None and any(marker in lower for marker in SETUP_MARKERS):
            setup_seconds = max(0.0, (event.timestamp - session.start).total_seconds())

        for match in MODE_RE.finditer(event.message):
            mode = match.group(1).upper()
            if not modes or modes[-1] != mode:
                modes.append(mode)

        # A log line can contain both a mode name and a byte count, so byte
        # extraction must not depend on the event's primary classification.
        for match in BYTES_RE.finditer(event.message):
            bytes_seen += int(match.group("count"))

    return SessionMetrics(
        peer=session.peer,
        result=session.result,
        duration_seconds=session.duration_seconds,
        setup_seconds=setup_seconds,
        bytes_seen=bytes_seen,
        retries=retries,
        mode_upgrades=upgrades,
        mode_downgrades=downgrades,
        initial_mode=modes[0] if modes else None,
        final_mode=modes[-1] if modes else None,
        modes_seen=modes,
    )


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"

    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours:d}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes:d}m {secs:02d}s"
    return f"{seconds:.1f}s"


def format_bytes(count: int) -> str:
    if count >= 1024 * 1024:
        return f"{count / (1024 * 1024):.2f} MiB"
    if count >= 1024:
        return f"{count / 1024:.2f} KiB"
    return f"{count} B"
