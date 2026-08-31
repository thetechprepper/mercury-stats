# Mercury HF Session Analyzer

A small, dependency-free terminal utility for scanning a Mercury HF log,
finding ARQ sessions, and selecting a session from a curses interface.

This is intentionally a **baseline** project. The parser is designed around
the Mercury CLI log patterns seen so far and keeps every raw event line so
the metrics can be tightened as more real-world logs are tested.

## Requirements

- Linux
- Python 3.10+
- Python `curses` module (normally included with Python on Linux)

No pip packages, database, web server, or GUI toolkit are required.

## Project layout

```text
mercury-stats/
├── mercury_stats.py
├── parser.py
├── metrics.py
├── models.py
├── README.md
└── tests/
    ├── sample.log
    └── test_parser.py
```

## Run

```bash
chmod +x mercury_stats.py
./mercury_stats.py /path/to/mercury.log
```

or:

```bash
python3 mercury_stats.py /path/to/mercury.log
```

## Controls

- `Up` / `Down` or `k` / `j`: select session
- `Enter`: view session metrics
- `Esc` / `Backspace`: return to session list
- `Q`: quit

## Current baseline metrics

- Peer callsign
- Session result
- Start/end time
- Session duration
- Connection setup time when an establishment marker is present
- Bytes observed in recognized log lines
- Retry count
- Mode upgrade/downgrade count
- Initial/final mode
- Sequence of modes seen

## Important limitation

The exact Mercury log vocabulary is still being characterized. In
particular, byte counters, connection-establishment markers, retry wording,
and the payload-mode ladder should be verified against additional real logs
before treating every metric as authoritative.

The parser currently starts a session when it sees:

```text
CONNECT <local-callsign> <peer-callsign>
```

and normally closes it at:

```text
DISCONNECT
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```
