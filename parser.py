from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from models import Event, Session


TIMESTAMP_RE = re.compile(
    r"^(?P<time>\d{2}:\d{2}:\d{2}\.\d{3})\s+\[\+(?P<offset>\d+\.\d+)s\]"
)

CONNECT_RE = re.compile(
    r"\bCONNECT\s+(?P<local>[A-Z0-9/-]+)\s+(?P<peer>[A-Z0-9/-]+)\b",
    re.IGNORECASE,
)

DISCONNECT_RE = re.compile(r"\bDISCONNECT\b", re.IGNORECASE)

PEER_RE = re.compile(
    r"\bpeer(?:\s+callsign)?\s*[:=]\s*(?P<peer>[A-Z0-9/-]+)\b",
    re.IGNORECASE,
)

MODE_RE = re.compile(r"\b(DATAC\d+|QAM16C2)\b", re.IGNORECASE)

BYTES_RE = re.compile(
    r"\b(?P<count>\d+)\s*(?:bytes?|B)\b",
    re.IGNORECASE,
)

RETRY_RE = re.compile(r"\bretr(?:y|ies|ansmit|ansmission)", re.IGNORECASE)

SUCCESS_WORDS = (
    "session complete",
    "transfer complete",
    "completed successfully",
    "disconnect complete",
    "arq session ended",
)

FAIL_WORDS = (
    "timeout",
    "connection failed",
    "connect failed",
    "aborted",
    "no-progress timeout",
    "peer lost",
)


def parse_timestamp(line: str, base_date: datetime) -> datetime | None:
    match = TIMESTAMP_RE.search(line)
    if not match:
        return None

    t = datetime.strptime(match.group("time"), "%H:%M:%S.%f").time()
    return base_date.replace(
        hour=t.hour,
        minute=t.minute,
        second=t.second,
        microsecond=t.microsecond,
    )


def classify_event(line: str) -> str:
    lower = line.lower()

    if CONNECT_RE.search(line):
        return "connect"
    if DISCONNECT_RE.search(line):
        return "disconnect"
    if "ptt on" in lower or "tx enabled" in lower:
        return "tx"
    if "ptt off" in lower or "tx disabled" in lower:
        return "rx"
    if MODE_RE.search(line):
        if "downgrade" in lower:
            return "mode_downgrade"
        if "upgrade" in lower:
            return "mode_upgrade"
        return "mode"
    if RETRY_RE.search(line):
        return "retry"
    if BYTES_RE.search(line):
        return "data"
    if any(word in lower for word in FAIL_WORDS):
        return "failure"
    if any(word in lower for word in SUCCESS_WORDS):
        return "success"
    return "other"


def extract_peer(line: str) -> str | None:
    match = CONNECT_RE.search(line)
    if match:
        return match.group("peer").upper()

    match = PEER_RE.search(line)
    if match:
        return match.group("peer").upper()

    return None


def parse_lines(lines: Iterable[str], base_date: datetime | None = None) -> list[Session]:
    """
    Parse Mercury log lines into coarse ARQ sessions.

    Baseline behavior:
      * A line containing 'CONNECT <local> <peer>' starts a session.
      * A line containing 'DISCONNECT' ends the current session.
      * Events between those markers are retained for metrics.
      * If a second CONNECT is seen before DISCONNECT, the previous
        session is closed immediately before the new session begins.

    Mercury's exact log wording may evolve. The parser intentionally keeps
    the raw line for every event so patterns can be tightened later without
    losing information.
    """
    if base_date is None:
        base_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    sessions: list[Session] = []
    current: Session | None = None
    last_timestamp: datetime | None = None

    for raw in lines:
        line = raw.rstrip("\n")
        timestamp = parse_timestamp(line, base_date)
        if timestamp is None:
            continue

        # Handle midnight rollover for logs spanning more than one day.
        if last_timestamp and timestamp < last_timestamp - timedelta(hours=12):
            base_date = base_date + timedelta(days=1)
            timestamp = parse_timestamp(line, base_date)
        last_timestamp = timestamp

        connect_match = CONNECT_RE.search(line)
        if connect_match:
            if current is not None:
                current.end = timestamp
                if current.result == "UNKNOWN":
                    current.result = "INCOMPLETE"
                sessions.append(current)

            current = Session(
                peer=connect_match.group("peer").upper(),
                start=timestamp,
            )
            current.events.append(
                Event(timestamp, "connect", line, line)
            )
            continue

        if current is None:
            continue

        kind = classify_event(line)
        current.events.append(Event(timestamp, kind, line, line))

        if kind == "failure":
            current.result = "FAILED"
        elif kind == "success":
            current.result = "SUCCESS"

        if DISCONNECT_RE.search(line):
            current.end = timestamp
            if current.result == "UNKNOWN":
                current.result = "SUCCESS"
            sessions.append(current)
            current = None

    if current is not None:
        if current.events:
            current.end = current.events[-1].timestamp
        current.result = "INCOMPLETE" if current.result == "UNKNOWN" else current.result
        sessions.append(current)

    return sessions


def parse_file(path: str | Path) -> list[Session]:
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return parse_lines(fh)
