#!/usr/bin/env python3
from __future__ import annotations

import argparse
import curses
import sys
from pathlib import Path

from metrics import calculate_metrics, format_bytes, format_duration
from parser import parse_file


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


def session_label(session) -> str:
    start = session.start.strftime("%Y-%m-%d %H:%M:%S")
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


def detail_screen(stdscr, session) -> None:
    metrics = calculate_metrics(session)

    lines = [
        ("Peer", metrics.peer),
        ("Result", metrics.result),
        ("Start", session.start.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]),
        ("End", session.end.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if session.end else "-"),
        ("Duration", format_duration(metrics.duration_seconds)),
        ("Connection setup", format_duration(metrics.setup_seconds)),
        ("Bytes observed", format_bytes(metrics.bytes_seen)),
        ("Retries", str(metrics.retries)),
        ("Mode upgrades", str(metrics.mode_upgrades)),
        ("Mode downgrades", str(metrics.mode_downgrades)),
        ("Initial mode", metrics.initial_mode or "-"),
        ("Final mode", metrics.final_mode or "-"),
        ("Modes seen", " → ".join(metrics.modes_seen) if metrics.modes_seen else "-"),
    ]

    while True:
        stdscr.erase()
        safe_addstr(stdscr, 0, 1, f"Session: {session.peer}", curses.A_BOLD)
        safe_addstr(stdscr, 1, 1, "-" * 78)

        row = 3
        for label, value in lines:
            safe_addstr(stdscr, row, 2, f"{label:<20} {value}")
            row += 1

        height, _ = stdscr.getmaxyx()
        safe_addstr(stdscr, height - 1, 1, "Esc/Backspace Back   Q Quit")
        stdscr.refresh()

        key = stdscr.getch()
        if key in (27, curses.KEY_BACKSPACE, 127):
            return
        if key in (ord("q"), ord("Q")):
            raise KeyboardInterrupt


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
        description="Scan a Mercury HF log and select ARQ sessions in a curses interface."
    )
    parser.add_argument(
        "logfile",
        nargs="?",
        type=Path,
        default=Path("~/.local/share/emcomm-tools/mercury/session.log").expanduser(),
        help=(
            "Path to the Mercury log file "
            "(default: ~/.local/share/emcomm-tools/mercury/session.log)"
        ),
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    if not args.logfile.is_file():
        print(f"error: log file not found: {args.logfile}", file=sys.stderr)
        return 2

    sessions = parse_file(args.logfile)
    if not sessions:
        print(
            "No sessions found. The baseline parser currently looks for "
            "'CONNECT <local> <peer>' markers.",
            file=sys.stderr,
        )
        return 1

    curses.wrapper(run_ui, args.logfile, sessions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
