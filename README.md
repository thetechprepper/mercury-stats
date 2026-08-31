# Mercury HF Session Analyzer

A small, dependency-free terminal utility for scanning a Mercury HF JSONL
log, finding ARQ sessions, and selecting a session from a curses interface.

Mercury Stats intentionally supports **JSONL only**. Run Mercury with `-J`
and `-L` so the log contains machine-readable records with an absolute
timestamp.

## Mercury example

```bash
mercury \
  -C ~/.local/share/emcomm-tools/mercury/mercury.ini.arq \
  -J \
  -L ~/.local/share/emcomm-tools/mercury/session.json \
  -i plughw:1,0 \
  -o plughw:1,0
```

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
    ├── sample.json
    └── test_parser.py
```

## Run

By default, the application reads:

```text
~/.local/share/emcomm-tools/mercury/session.json
```

So normally:

```bash
chmod +x mercury_stats.py
./mercury_stats.py
```

or:

```bash
python3 mercury_stats.py
```

To analyze a different JSONL log:

```bash
python3 mercury_stats.py /path/to/session.json
```

## Controls

- `Up` / `Down` or `k` / `j`: select session
- `Enter`: view session metrics
- `Esc` / `Backspace`: return to session list
- `Q`: quit

## Timestamp handling

Mercury's JSONL field `t` is treated as a Unix epoch timestamp in
milliseconds. It is preserved internally as UTC and displayed in the
computer's local timezone.

The `up` field is not currently required by the baseline parser.

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

## Session boundaries

A session starts when the Mercury JSONL `m` field contains:

```text
CONNECT <local-callsign> <peer-callsign>
```

A session ends when Mercury logs:

```text
Disconnected
```

A bare disconnect is reported as `DISCONNECTED`; it is not assumed to mean
that an application-level transfer succeeded.

## Invalid input

Legacy text `.log` files are not supported. Non-JSONL input fails with:

```text
error: Mercury Stats requires a JSONL log generated with Mercury -J.
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```
