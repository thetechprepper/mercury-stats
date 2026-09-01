from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from models import Event, Session


COMMAND_PREFIX = "Command received: "
CONNECT_COMMAND_PREFIX = "Command received: CONNECT "
INCOMING_CONNECTION_PREFIX = "Incoming connection from "

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


def connect_callsigns(message: str) -> tuple[str, str] | None:
    """
    Extract local and remote callsigns from Mercury's CONNECT command.

    Expected message:
        Command received: CONNECT <local> <peer>
    """
    if not message.startswith(CONNECT_COMMAND_PREFIX):
        return None

    parts = message[len(CONNECT_COMMAND_PREFIX):].split()
    if len(parts) < 2:
        return None

    return parts[0].upper(), parts[1].upper()


def incoming_callsigns(message: str) -> tuple[str, str] | None:
    """
    Extract local and remote callsigns from Mercury's inbound connection notice.

    Expected message:
        Incoming connection from <peer> on <local> (pending)

    Returns:
        (local, peer)
    """
    if not message.startswith(INCOMING_CONNECTION_PREFIX):
        return None

    remainder = message[len(INCOMING_CONNECTION_PREFIX):]
    peer, separator, local_part = remainder.partition(" on ")
    if not separator:
        return None

    local = local_part.removesuffix(" (pending)").strip()
    peer = peer.strip()

    if not local or not peer:
        return None

    return local.upper(), peer.upper()


def classify_event(message: str) -> str:
    """
    Classify only known Mercury message forms.

    This deliberately uses exact/prefix string handling rather than regex.
    The JSON object itself is parsed by json.loads().
    """
    lower = message.lower()

    if message.startswith(CONNECT_COMMAND_PREFIX):
        return "connect_command"
    if message.startswith(INCOMING_CONNECTION_PREFIX):
        return "incoming_connection"
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
    if message.startswith("MODE_REQ: peer TX mode "):
        return "peer_tx_mode_request"
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
        if event.kind in ("connect_command", "incoming_connection"):
            if event.kind == "connect_command":
                callsigns = connect_callsigns(event.message)
            else:
                callsigns = incoming_callsigns(event.message)

            if callsigns is None:
                continue

            mycall, peer = callsigns

            if current is not None:
                _finalize_session(sessions, current, fallback_end=event.timestamp)

            current = Session(mycall=mycall, peer=peer, start=event.timestamp)
            current.events.append(event)
            continue

        if current is None:
            continue

        # Mercury may emit the authoritative disconnect summary after the
        # "Disconnected" event. Keep the ended session pending long enough to
        # consume that summary, but do not attach unrelated post-session events.
        if current.end is not None:
            if event.kind == "disconnect_summary":
                current.events.append(event)
                if current.result == "UNKNOWN":
                    current.result = "DISCONNECTED"
                sessions.append(current)
                current = None
            continue

        current.events.append(event)

        if event.kind == "failure":
            current.result = "FAILED"

        # A DISCONNECT command is only a request. The actual session end is
        # Mercury's "Disconnected" event. If the disconnect summary was
        # already logged, the session can be finalized immediately. Otherwise
        # keep it pending in case Mercury logs the summary next.
        if event.kind == "disconnected":
            current.end = event.timestamp
            if current.result == "UNKNOWN":
                current.result = "DISCONNECTED"

            if any(item.kind == "disconnect_summary" for item in current.events):
                sessions.append(current)
                current = None
            continue

        # Disconnect summary contains authoritative counters/reason, but it
        # does not define the actual end of the session. Mercury may emit the
        # summary before or after "Disconnected".
        if event.kind == "disconnect_summary":
            if current.result == "UNKNOWN":
                current.result = "DISCONNECTED"
            continue

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
        except json.JSONDecodeError:
            continue

        if not isinstance(record, dict):
            continue

        timestamp = parse_json_timestamp(record.get("t"))
        message = record.get("m")
        component = record.get("c", "")
        level = record.get("lv", "")
        uptime_ms = record.get("up")

        if timestamp is None:
            continue
        if not isinstance(message, str):
            continue
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
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return parse_json_lines(fh)
