# Mercury HF Session Analyzer

A small, dependency-free terminal utility for scanning a Mercury HF JSONL
log, finding ARQ sessions, and selecting a session from a curses interface.

## Input format

Mercury Stats supports **JSONL only**.

Run Mercury with `-J` and `-L`:

```bash
mercury \
  -C ~/.local/share/emcomm-tools/mercury/mercury.ini.arq \
  -J \
  -L ~/.local/share/emcomm-tools/mercury/session.json \
  -i plughw:1,0 \
  -o plughw:1,0
```

The application uses Python's `json.loads()` to parse each JSON object.
There is no legacy text-log parser and no regular-expression parser.

Mercury still places event-specific details inside the JSON `m` string.
Those known messages are interpreted with exact prefixes and
whitespace-separated `key=value` tokens.

## Default log

```text
~/.local/share/emcomm-tools/mercury/session.json
```

Run:

```bash
./mercury_stats.py
```

or:

```bash
python3 mercury_stats.py
```

Specify another JSONL log if needed:

```bash
python3 mercury_stats.py /path/to/session.json
```

## Session lifecycle

A session starts with the JSON message:

```text
Command received: CONNECT <local> <peer>
```

`Command received: DISCONNECT` is treated only as a disconnect request.

The actual session end is Mercury's:

```text
Disconnected
```

The parser records the following timing summary whenever it appears:

```text
disconnect reason=... tx_bytes=... rx_bytes=... frames_tx=... frames_rx=... retries=...
```

That summary is authoritative for the final byte, frame, retry, and
disconnect-reason counters. The session itself ends only at Mercury's
`Disconnected` event, regardless of whether the summary appears before
or after it.

## Report fields

- Peer
- Result / disconnect reason
- Start
- Connected
- End
- Duration
- Connection setup time
- TX bytes
- RX bytes
- Total bytes
- Retries
- Connect mode
- Payload-mode transitions
- Final TX data mode

Connect mode and payload/data mode are intentionally reported separately.

## Requirements

- Linux
- Python 3.10+
- Python `curses` module

No pip dependencies, database, web server, or GUI toolkit are required.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
