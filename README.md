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
- TX/RX ARQ data frames
- Retries
- Connect mode
- Payload-mode transitions
- Final TX data mode

Connect mode and payload/data mode are intentionally reported separately.


## FreeDV mode mapping

Mercury's ARQ timing/FSM messages use internal FreeDV numeric mode IDs.
Mercury Stats translates them using the definitions in Mercury's vendored
`modem/freedv/freedv_api.h`:

```text
10  DATAC1
12  DATAC3
18  DATAC4
19  DATAC13
22  DATAC15
23  DATAC16
24  DATAC17
25  QAM16C2
```

For example:

```text
MODE_ACK: payload mode 22 -> 12
```

is reported as:

```text
DATAC15 → DATAC3
```

Unknown IDs are displayed as `MODE_<id>` rather than guessed.

Source:
https://github.com/Rhizomatica/mercury/blob/mercuryv2/modem/freedv/freedv_api.h


## ARQ mode legend

The session detail screen includes a static Unicode legend for Mercury's
adaptive ARQ modes. Payload values are **ARQ payload bytes per frame**, which
match the data quantities reported in Mercury timing records such as
`tx_queue bytes=`.

```text
┌────┬─────────┬─────────┬──────────────────────────────────────┐
│ ID │ Mode    │ Payload │ Use / description                    │
├────┼─────────┼─────────┼──────────────────────────────────────┤
│ 22 │ DATAC15 │ 22 B    │ Payload; lowest SNR / ladder floor   │
│ 18 │ DATAC4  │ 46 B    │ Payload; low SNR                     │
│ 12 │ DATAC3  │ 118 B   │ Payload; default startup mode        │
│ 10 │ DATAC1  │ 502 B   │ Payload; +5 dB SNR                   │
│ 24 │ DATAC17 │ 1172 B  │ Payload; intermediate SNR (~+8 dB)   │
│ 25 │ QAM16C2 │ 1205 B  │ Payload; high SNR (~+15 dB)          │
│ 23 │ DATAC16 │ 6 B     │ Control; ARQ control channel         │
└────┴─────────┴─────────┴──────────────────────────────────────┘
```

Source:
https://github.com/Rhizomatica/mercury/blob/mercuryv2/mercury.1

## Requirements

- Linux
- Python 3.10+
- Python `curses` module

No pip dependencies, database, web server, or GUI toolkit are required.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
