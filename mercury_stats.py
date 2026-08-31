#!/usr/bin/env python3
from __future__ import annotations

import argparse
import curses
import sys
from pathlib import Path

from metrics import ARQ_MODE_LEGEND, calculate_metrics, format_bytes, format_duration
from parser import MercuryLogError, parse_file
from version import __version__


APP_TITLE = "Mercury HF Session Analyzer"


def safe_addstr(stdscr, y: int, x: int, text: str, attr: int = 0) -> None:
    height, width = stdscr.getmaxyx()
    if y < 0 or y >= height or x >= width:
        return

    max_len = max(0, width - x - 1)
    if max_len <= 0:
        return

    try:
        stdscr.addnstr(y, x, text, max_len, attr)
    except curses.error:
        pass


def draw_header(stdscr, path: Path, session_count: int) -> int:
    safe_addstr(stdscr, 0, 1, APP_TITLE, curses.A_BOLD)
    safe_addstr(stdscr, 1, 1, f"Log: {path}")
    safe_addstr(stdscr, 2, 1, f"Sessions found: {session_count}")
    safe_addstr(stdscr, 3, 1, "-" * 78)
    return 5


def display_timestamp(timestamp, milliseconds: bool = False) -> str:
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone()

    fmt = "%Y-%m-%d %H:%M:%S.%f" if milliseconds else "%Y-%m-%d %H:%M:%S"
    value = timestamp.strftime(fmt)
    if milliseconds:
        value = value[:-3]
    return value


def session_label(session) -> str:
    start = display_timestamp(session.start)
    duration = format_duration(session.duration_seconds)
    return f"{start:<20} {session.peer:<12} {duration:<10} {session.result}"


def session_list_screen(stdscr, path: Path, sessions) -> int | None:
    selected = 0
    top = 0

    while True:
        stdscr.erase()
        row = draw_header(stdscr, path, len(sessions))
        height, _ = stdscr.getmaxyx()
        visible = max(1, height - row - 2)

        if selected < top:
            top = selected
        elif selected >= top + visible:
            top = selected - visible + 1

        safe_addstr(
            stdscr,
            row - 1,
            1,
            f"{'Date/Time':<20} {'Peer':<12} {'Duration':<10} Result",
            curses.A_UNDERLINE,
        )

        for screen_index, session_index in enumerate(range(top, min(len(sessions), top + visible))):
            session = sessions[session_index]
            attr = curses.A_REVERSE if session_index == selected else curses.A_NORMAL
            safe_addstr(stdscr, row + screen_index, 1, session_label(session), attr)

        safe_addstr(stdscr, height - 1, 1, "↑/↓ Select   Enter View   Q Quit")
        stdscr.refresh()

        key = stdscr.getch()
        if key in (ord("q"), ord("Q")):
            return None
        if key in (curses.KEY_UP, ord("k")) and selected > 0:
            selected -= 1
        elif key in (curses.KEY_DOWN, ord("j")) and selected < len(sessions) - 1:
            selected += 1
        elif key in (curses.KEY_ENTER, 10, 13):
            return selected


def mode_legend_lines() -> list[str]:
    headers = ("ID", "Mode", "Payload", "Use / description")
    rows = [headers, *ARQ_MODE_LEGEND]

    widths = [
        max(len(str(row[column])) for row in rows)
        for column in range(len(headers))
    ]

    def border(left: str, middle: str, right: str, fill: str = "─") -> str:
        return (
            left
            + middle.join(fill * (width + 2) for width in widths)
            + right
        )

    def data_row(row) -> str:
        cells = [
            f" {str(value):<{width}} "
            for value, width in zip(row, widths)
        ]
        return "│" + "│".join(cells) + "│"

    return [
        border("┌", "┬", "┐"),
        data_row(headers),
        border("├", "┼", "┤"),
        *(data_row(row) for row in ARQ_MODE_LEGEND),
        border("└", "┴", "┘"),
    ]


def detail_screen(stdscr, session) -> None:
    metrics = calculate_metrics(session)

    transition_text = (
        " | ".join(metrics.payload_transitions)
        if metrics.payload_transitions
        else "-"
    )
    peer_transition_text = (
        " | ".join(metrics.peer_tx_requested_transitions)
        if metrics.peer_tx_requested_transitions
        else "-"
    )

    report_lines = [
        f"{'Peer':<20} {metrics.peer}",
        f"{'Result':<20} {metrics.result}",
        f"{'Start':<20} {display_timestamp(session.start, milliseconds=True)}",
        (
            f"{'Connected':<20} "
            f"{display_timestamp(metrics.connected_at, milliseconds=True) if metrics.connected_at else '-'}"
        ),
        f"{'End':<20} {display_timestamp(session.end, milliseconds=True) if session.end else '-'}",
        f"{'Duration':<20} {format_duration(metrics.duration_seconds)}",
        f"{'Connection setup':<20} {format_duration(metrics.setup_seconds)}",
        "",
        f"{'TX bytes':<20} {format_bytes(metrics.tx_bytes)}",
        f"{'RX bytes':<20} {format_bytes(metrics.rx_bytes)}",
        f"{'Total bytes':<20} {format_bytes(metrics.total_bytes)}",
        f"{'TX frames':<20} {metrics.frames_tx if metrics.frames_tx is not None else '-'}",
        f"{'RX frames':<20} {metrics.frames_rx if metrics.frames_rx is not None else '-'}",
        f"{'Retries':<20} {metrics.retries if metrics.retries is not None else '-'}",
        "",
        f"{'Control mode':<28} {metrics.connect_mode or '-'}",
        f"{'Local TX transitions':<28} {transition_text}",
        f"{'Peer TX transitions':<28} {peer_transition_text}",
        f"{'Final TX data mode':<28} {metrics.final_tx_mode or '-'}",
        "",
        "Note: Peer transitions only show requested transitions, not actual.",
        "",
        "Mercury ARQ Mode Legend",
        *mode_legend_lines(),
    ]

    top = 0

    while True:
        stdscr.erase()
        height, _ = stdscr.getmaxyx()
        visible_rows = max(1, height - 4)
        max_top = max(0, len(report_lines) - visible_rows)
        top = min(top, max_top)

        safe_addstr(stdscr, 0, 1, f"Session: {session.mycall} → {session.peer}", curses.A_BOLD)
        safe_addstr(stdscr, 1, 1, "-" * 78)

        for screen_row, line in enumerate(
            report_lines[top:top + visible_rows],
            start=3,
        ):
            safe_addstr(stdscr, screen_row, 2, line)

        footer = "Esc/Backspace Back   Q Quit"
        if max_top:
            footer = "↑/↓ Scroll   " + footer

        safe_addstr(stdscr, height - 1, 1, footer)
        stdscr.refresh()

        key = stdscr.getch()
        if key in (27, curses.KEY_BACKSPACE, 127):
            return
        if key in (ord("q"), ord("Q")):
            raise KeyboardInterrupt
        if key in (curses.KEY_UP, ord("k")) and top > 0:
            top -= 1
        elif key in (curses.KEY_DOWN, ord("j")) and top < max_top:
            top += 1
        elif key == curses.KEY_PPAGE:
            top = max(0, top - visible_rows)
        elif key == curses.KEY_NPAGE:
            top = min(max_top, top + visible_rows)


def run_ui(stdscr, path: Path, sessions) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)

    while True:
        selected = session_list_screen(stdscr, path, sessions)
        if selected is None:
            return

        try:
            detail_screen(stdscr, sessions[selected])
        except KeyboardInterrupt:
            return


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan a Mercury HF JSONL log and select ARQ sessions in a curses interface."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"mercury-stats {__version__}",
    )
    parser.add_argument(
        "logfile",
        nargs="?",
        type=Path,
        default=Path("~/.local/share/emcomm-tools/mercury/session.json").expanduser(),
        help=(
            "Path to the Mercury log file "
            "(default: ~/.local/share/emcomm-tools/mercury/session.json)"
        ),
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    if not args.logfile.is_file():
        print(f"error: log file not found: {args.logfile}", file=sys.stderr)
        return 2

    try:
        sessions = parse_file(args.logfile)
    except (MercuryLogError, UnicodeDecodeError) as exc:
        print(
            "error: Mercury Stats requires a JSONL log generated with Mercury -J.",
            file=sys.stderr,
        )
        print(f"detail: {exc}", file=sys.stderr)
        return 2

    if not sessions:
        print(
            "No sessions found. The parser looks for "
            "'CONNECT <local> <peer>' in Mercury JSONL message fields.",
            file=sys.stderr,
        )
        return 1

    curses.wrapper(run_ui, args.logfile, sessions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
