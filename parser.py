from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from models import Event, Session


CONNECT_RE = re.compile(
    r"\bCONNECT\s+(?P<local>[A-Z0-9/-]+)\s+(?P<peer>[A-Z0-9/-]+)\b",
    re.IGNORECASE,
)

DISCONNECT_RE = re.compile(r"\bDISCONNECT(?:ED)?\b", re.IGNORECASE)

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


class MercuryLogError(ValueError):
    """Raised when a Mercury JSONL log cannot be parsed."""


def parse_json_timestamp(value: object) -> datetime | None:
    """
    Mercury JSONL field "t" is Unix epoch time in milliseconds.

    Return an aware UTC datetime so the actual calendar date is preserved.
    """
    if not isinstance(value, (int, float)):
        return None

    try:
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def classify_event(message: str) -> str:
    lower = message.lower()

    if CONNECT_RE.search(message):
        return "connect"
    if DISCONNECT_RE.search(message):
        return "disconnect"
    if "ptt on" in lower or "tx enabled" in lower:
        return "tx"
    if "ptt off" in lower or "tx disabled" in lower:
        return "rx"
    if MODE_RE.search(message):
        if "downgrade" in lower:
            return "mode_downgrade"
        if "upgrade" in lower:
            return "mode_upgrade"
        return "mode"
    if RETRY_RE.search(message):
        return "retry"
    if BYTES_RE.search(message):
        return "data"
    if any(word in lower for word in FAIL_WORDS):
        return "failure"
    if any(word in lower for word in SUCCESS_WORDS):
        return "success"
    return "other"


def extract_peer(message: str) -> str | None:
    match = CONNECT_RE.search(message)
    if match:
        return match.group("peer").upper()

    match = PEER_RE.search(message)
    if match:
        return match.group("peer").upper()

    return None


def _parse_events(events: Iterable[tuple[datetime, str, str]]) -> list[Session]:
    sessions: list[Session] = []
    current: Session | None = None

    for timestamp, message, raw_line in events:
        connect_match = CONNECT_RE.search(message)
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
                Event(timestamp, "connect", message, raw_line)
            )
            continue

        if current is None:
            continue

        kind = classify_event(message)
        current.events.append(Event(timestamp, kind, message, raw_line))

        if kind == "failure":
            current.result = "FAILED"
        elif kind == "success":
            current.result = "SUCCESS"

        if DISCONNECT_RE.search(message):
            current.end = timestamp
            if current.result == "UNKNOWN":
                current.result = "DISCONNECTED"
            sessions.append(current)
            current = None

    if current is not None:
        if current.events:
            current.end = current.events[-1].timestamp
        current.result = "INCOMPLETE" if current.result == "UNKNOWN" else current.result
        sessions.append(current)

    return sessions


def parse_json_lines(lines: Iterable[str]) -> list[Session]:
    normalized: list[tuple[datetime, str, str]] = []
    saw_nonempty = False
    saw_valid_json_record = False

    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue

        saw_nonempty = True

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MercuryLogError(
                f"line {line_number}: invalid JSONL ({exc.msg})"
            ) from exc

        if not isinstance(record, dict):
            raise MercuryLogError(
                f"line {line_number}: expected a JSON object"
            )

        saw_valid_json_record = True

        timestamp = parse_json_timestamp(record.get("t"))
        message = record.get("m")

        if timestamp is None:
            raise MercuryLogError(
                f"line {line_number}: missing or invalid Mercury 't' timestamp"
            )

        if not isinstance(message, str):
            raise MercuryLogError(
                f"line {line_number}: missing or invalid Mercury 'm' message"
            )

        normalized.append((timestamp, message, line))

    if saw_nonempty and not saw_valid_json_record:
        raise MercuryLogError("no valid Mercury JSONL records found")

    return _parse_events(normalized)


def parse_file(path: str | Path) -> list[Session]:
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="strict") as fh:
        return parse_json_lines(fh)
