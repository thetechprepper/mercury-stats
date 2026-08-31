from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from models import Session


# Mercury logs internal FreeDV mode IDs in payload_mode / MODE_ACK /
# Mode negotiation messages. These values come from Mercury's vendored
# modem/freedv/freedv_api.h definitions.
FREEDV_MODE_NAMES = {
    "10": "DATAC1",
    "12": "DATAC3",
    "18": "DATAC4",
    "19": "DATAC13",
    "22": "DATAC15",
    "23": "DATAC16",
    "24": "DATAC17",
    "25": "QAM16C2",
}


# ARQ mode legend from Mercury's current mercury.1 documentation.
# Payload is ARQ payload bytes per frame, not the larger raw FreeDV frame size.
# Ordered by the adaptive payload ladder, followed by the control mode.
ARQ_MODE_LEGEND = (
    ("22", "DATAC15", "22 B", "Payload; lowest SNR / ladder floor"),
    ("18", "DATAC4", "46 B", "Payload; low SNR"),
    ("12", "DATAC3", "118 B", "Payload; default startup mode"),
    ("10", "DATAC1", "502 B", "Payload; +5 dB SNR"),
    ("24", "DATAC17", "1172 B", "Payload; intermediate SNR (~+8 dB)"),
    ("25", "QAM16C2", "1205 B", "Payload; high SNR (~+15 dB)"),
    ("23", "DATAC16", "6 B", "Control; ARQ control channel"),
)


def mode_name(mode_id: str) -> str:
    """Return the DATAC/QAM name for a Mercury internal FreeDV mode ID."""
    return FREEDV_MODE_NAMES.get(mode_id, f"MODE_{mode_id}")


@dataclass
class SessionMetrics:
    peer: str
    result: str
    connected_at: datetime | None
    duration_seconds: Optional[float]
    setup_seconds: Optional[float]
    disconnect_reason: str | None
    tx_bytes: int | None
    rx_bytes: int | None
    total_bytes: int | None
    retries: int | None
    frames_tx: int | None
    frames_rx: int | None
    connect_mode: str | None
    payload_transitions: list[str]
    peer_tx_requested_transitions: list[str]
    final_tx_mode: str | None


def key_value_tokens(message: str) -> dict[str, str]:
    """
    Parse whitespace-separated key=value tokens from Mercury's message field.

    Punctuation surrounding a value is stripped conservatively. This is
    message-token parsing, not legacy text-log parsing and not regex.
    """
    values: dict[str, str] = {}

    for token in message.split():
        if "=" not in token:
            continue

        key, value = token.split("=", 1)
        key = key.strip("(),:")
        value = value.strip("(),")

        if key:
            values[key] = value

    return values


def int_value(values: dict[str, str], key: str) -> int | None:
    raw = values.get(key)
    if raw is None:
        return None

    try:
        return int(raw)
    except ValueError:
        return None


def payload_transition(message: str) -> str | None:
    prefix = "MODE_ACK: payload mode "
    if not message.startswith(prefix):
        return None

    parts = message[len(prefix):].split()
    if len(parts) >= 3 and parts[1] == "->":
        old_id = parts[0]
        new_id = parts[2]
        return f"{mode_name(old_id)} → {mode_name(new_id)}"

    return None


def peer_tx_requested_transition(message: str) -> str | None:
    prefix = "MODE_REQ: peer TX mode "
    if not message.startswith(prefix):
        return None

    # Expected form:
    # MODE_REQ: peer TX mode 22 -> 12 (my TX mode 22 unchanged)
    parts = message[len(prefix):].split()
    if len(parts) >= 3 and parts[1] == "->":
        old_id = parts[0]
        new_id = parts[2]
        return f"{mode_name(old_id)} → {mode_name(new_id)}"

    return None


def calculate_metrics(session: Session) -> SessionMetrics:
    connected_at = None
    disconnect_reason = None

    # Final disconnect summary values are authoritative when present.
    summary_tx_bytes = None
    summary_rx_bytes = None
    summary_retries = None
    summary_frames_tx = None
    summary_frames_rx = None

    # Fallback cumulative counters from individual timing events.
    fallback_tx_bytes = None
    fallback_rx_bytes = None
    fallback_retries = None

    connect_mode = None
    transitions: list[str] = []
    peer_requested_transitions: list[str] = []
    final_tx_mode = None

    for event in session.events:
        message = event.message

        if event.kind == "connected" and connected_at is None:
            connected_at = event.timestamp

        elif event.kind == "connect_mode":
            value = message.removeprefix("connect mode=").strip()
            if value:
                connect_mode = value

        elif event.kind == "peer_tx_mode_request":
            transition = peer_tx_requested_transition(message)
            if transition and transition not in peer_requested_transitions:
                peer_requested_transitions.append(transition)

        elif event.kind == "payload_mode_ack":
            transition = payload_transition(message)
            if transition and transition not in transitions:
                transitions.append(transition)

        elif event.kind == "tx_queue":
            values = key_value_tokens(message)
            mode = values.get("mode")
            if mode:
                final_tx_mode = mode

            tx_total = int_value(values, "tx_total")
            if tx_total is not None:
                fallback_tx_bytes = tx_total

        elif event.kind == "data_rx":
            values = key_value_tokens(message)
            rx_total = int_value(values, "rx_total")
            if rx_total is not None:
                fallback_rx_bytes = rx_total

        elif event.kind == "olla_state":
            values = key_value_tokens(message)
            retry_count = int_value(values, "retries")
            if retry_count is not None:
                fallback_retries = retry_count

        elif event.kind == "disconnect_summary":
            values = key_value_tokens(message)
            disconnect_reason = values.get("reason")
            summary_tx_bytes = int_value(values, "tx_bytes")
            summary_rx_bytes = int_value(values, "rx_bytes")
            summary_frames_tx = int_value(values, "frames_tx")
            summary_frames_rx = int_value(values, "frames_rx")
            summary_retries = int_value(values, "retries")

    tx_bytes = summary_tx_bytes if summary_tx_bytes is not None else fallback_tx_bytes
    rx_bytes = summary_rx_bytes if summary_rx_bytes is not None else fallback_rx_bytes
    retries = summary_retries if summary_retries is not None else fallback_retries

    total_bytes = None
    if tx_bytes is not None or rx_bytes is not None:
        total_bytes = (tx_bytes or 0) + (rx_bytes or 0)

    setup_seconds = None
    if connected_at is not None:
        setup_seconds = max(0.0, (connected_at - session.start).total_seconds())

    result = session.result
    if disconnect_reason:
        result = f"DISCONNECTED ({disconnect_reason})"

    return SessionMetrics(
        peer=session.peer,
        result=result,
        connected_at=connected_at,
        duration_seconds=session.duration_seconds,
        setup_seconds=setup_seconds,
        disconnect_reason=disconnect_reason,
        tx_bytes=tx_bytes,
        rx_bytes=rx_bytes,
        total_bytes=total_bytes,
        retries=retries,
        frames_tx=summary_frames_tx,
        frames_rx=summary_frames_rx,
        connect_mode=connect_mode,
        payload_transitions=transitions,
        peer_tx_requested_transitions=peer_requested_transitions,
        final_tx_mode=final_tx_mode,
    )


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"

    if seconds < 60:
        return f"{seconds:.1f}s"

    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {secs:.1f}s"

    hours, remaining_minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(remaining_minutes):02d}m {secs:.1f}s"


def format_bytes(count: int | None) -> str:
    if count is None:
        return "-"

    if count >= 1024 * 1024:
        return f"{count} B ({count / (1024 * 1024):.2f} MiB)"
    if count >= 1024:
        return f"{count} B ({count / 1024:.2f} KiB)"
    return f"{count} B"
