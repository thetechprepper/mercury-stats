from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from models import Event, Session


COMMAND_PREFIX = "Command received: "
CONNECT_COMMAND_PREFIX = "Command received: CONNECT "

FAIL_WORDS = (
    "connection failed",
    "connect failed",
    "no-progress timeout",
    "peer lost",
    "aborted",
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


def connect_peer(message: str) -> str | None:
    """
    Extract the remote peer from Mercury's CONNECT control command.

    Expected message:
        Command received: CONNECT <local> <peer>
    """
    if not message.startswith(CONNECT_COMMAND_PREFIX):
        return None

    parts = message[len(CONNECT_COMMAND_PREFIX):].split()
    if len(parts) < 2:
        return None

    return parts[1].upper()


def classify_event(message: str) -> str:
    """
    Classify only known Mercury message forms.

    This deliberately uses exact/prefix string handling rather than regex.
    The JSON object itself is parsed by json.loads().
    """
    lower = message.lower()

    if message.startswith(CONNECT_COMMAND_PREFIX):
        return "connect_command"
    if message.startswith("Connected to "):
        return "connected"
    if message == "Disconnected":
        return "disconnected"
    if message.startswith("disconnect reason="):
        return "disconnect_summary"
    if message == "TX enabled (PTT ON)":
        return "tx_start"
    if message == "TX disabled (PTT OFF)":
        return "tx_end"
    if message.startswith("connect mode="):
        return "connect_mode"
    if message.startswith("MODE_ACK: payload mode "):
        return "payload_mode_ack"
    if message.startswith("Mode negotiation: "):
        return "payload_mode_negotiation"
    if message.startswith("tx_queue "):
        return "tx_queue"
    if message.startswith("data_rx "):
        return "data_rx"
    if message.startswith("ack_rx "):
        return "ack_rx"
    if message.startswith("ack_tx "):
        return "ack_tx"
    if message.startswith("OLLA-state: "):
        return "olla_state"
    if any(word in lower for word in FAIL_WORDS):
        return "failure"
    return "other"


def _finalize_session(
    sessions: list[Session],
    current: Session,
    fallback_end: datetime | None = None,
) -> None:
    if current.end is None:
        current.end = fallback_end
    if current.result == "UNKNOWN":
        current.result = "INCOMPLETE"
    sessions.append(current)


def _parse_events(events: Iterable[Event]) -> list[Session]:
    sessions: list[Session] = []
    current: Session | None = None

    for event in events:
        if event.kind == "connect_command":
            peer = connect_peer(event.message)
            if peer is None:
                continue

            if current is not None:
                _finalize_session(sessions, current, fallback_end=event.timestamp)

            current = Session(peer=peer, start=event.timestamp)
            current.events.append(event)
            continue

        if current is None:
            continue

        current.events.append(event)

        if event.kind == "failure":
            current.result = "FAILED"

        # A DISCONNECT command is only a request. The actual session end is
        # Mercury's "Disconnected" event.
        if event.kind == "disconnected":
            current.end = event.timestamp
            if current.result == "UNKNOWN":
                current.result = "DISCONNECTED"
            continue

        # Keep the session open through the final timing summary so its
        # authoritative counters remain part of the session.
        if event.kind == "disconnect_summary":
            if current.end is None:
                current.end = event.timestamp
            if current.result == "UNKNOWN":
                current.result = "DISCONNECTED"
            sessions.append(current)
            current = None

    if current is not None:
        fallback_end = current.events[-1].timestamp if current.events else current.start
        _finalize_session(sessions, current, fallback_end=fallback_end)

    return sessions


def parse_json_lines(lines: Iterable[str]) -> list[Session]:
    events: list[Event] = []

    for line_number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue

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

        timestamp = parse_json_timestamp(record.get("t"))
        message = record.get("m")
        component = record.get("c", "")
        level = record.get("lv", "")
        uptime_ms = record.get("up")

        if timestamp is None:
            raise MercuryLogError(
                f"line {line_number}: missing or invalid Mercury 't' timestamp"
            )
        if not isinstance(message, str):
            raise MercuryLogError(
                f"line {line_number}: missing or invalid Mercury 'm' message"
            )
        if not isinstance(component, str):
            component = ""
        if not isinstance(level, str):
            level = ""
        if not isinstance(uptime_ms, int):
            uptime_ms = None

        events.append(
            Event(
                timestamp=timestamp,
                kind=classify_event(message),
                message=message,
                component=component,
                level=level,
                uptime_ms=uptime_ms,
                raw_line=line,
            )
        )

    return _parse_events(events)


def parse_file(path: str | Path) -> list[Session]:
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="strict") as fh:
        return parse_json_lines(fh)
