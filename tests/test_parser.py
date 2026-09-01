import sys
import tempfile
import unittest
from datetime import timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from metrics import ARQ_MODE_LEGEND, FREEDV_MODE_NAMES, calculate_metrics, format_bytes, mode_name
from parser import MercuryLogError, parse_file, parse_json_timestamp
from version import __version__


class JsonParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = parse_file(ROOT / "tests" / "sample.json")
        cls.session = cls.sessions[0]
        cls.metrics = calculate_metrics(cls.session)

    def test_one_session(self):
        self.assertEqual(len(self.sessions), 1)

    def test_peer(self):
        self.assertEqual(self.session.peer, "KT7RUN")

    def test_mycall(self):
        self.assertEqual(self.session.mycall, "KT7RUN-2")

    def test_epoch_timestamp(self):
        dt = parse_json_timestamp(1788202864498)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_session_ends_on_disconnected_not_summary(self):
        self.assertEqual(
            self.session.end,
            parse_json_timestamp(1788203177490),
        )

    def test_duration(self):
        self.assertAlmostEqual(self.session.duration_seconds, 312.992, places=3)

    def test_setup_time(self):
        self.assertAlmostEqual(self.metrics.setup_seconds, 7.839, places=3)

    def test_disconnect_reason(self):
        self.assertEqual(self.metrics.disconnect_reason, "rx_disconnect")
        self.assertEqual(self.metrics.result, "DISCONNECTED (rx_disconnect)")

    def test_authoritative_byte_counters(self):
        self.assertEqual(self.metrics.tx_bytes, 9679)
        self.assertEqual(self.metrics.rx_bytes, 110)
        self.assertEqual(self.metrics.total_bytes, 9789)

    def test_authoritative_retry_counter(self):
        self.assertEqual(self.metrics.retries, 0)

    def test_frames(self):
        self.assertEqual(self.metrics.frames_tx, 19)
        self.assertEqual(self.metrics.frames_rx, 4)

    def test_modes(self):
        self.assertEqual(self.metrics.connect_mode, "DATAC16")
        self.assertEqual(
            self.metrics.payload_transitions,
            [
                "DATAC15 → DATAC3",
                "DATAC3 → DATAC1",
                "DATAC1 → DATAC17",
            ],
        )
        self.assertEqual(
            self.metrics.peer_tx_requested_transitions,
            ["DATAC15 → DATAC3"],
        )
        self.assertEqual(self.metrics.final_tx_mode, "DATAC17")

    def test_freedv_mode_map(self):
        self.assertEqual(mode_name("10"), "DATAC1")
        self.assertEqual(mode_name("12"), "DATAC3")
        self.assertEqual(mode_name("18"), "DATAC4")
        self.assertEqual(mode_name("19"), "DATAC13")
        self.assertEqual(mode_name("22"), "DATAC15")
        self.assertEqual(mode_name("23"), "DATAC16")
        self.assertEqual(mode_name("24"), "DATAC17")
        self.assertEqual(mode_name("25"), "QAM16C2")

    def test_unknown_mode_is_visible(self):
        self.assertEqual(mode_name("999"), "MODE_999")

    def test_arq_mode_legend(self):
        self.assertEqual(
            ARQ_MODE_LEGEND,
            (
                ("22", "DATAC15", "30 B", "Payload; lowest SNR / ladder floor"),
                ("18", "DATAC4", "54 B", "Payload; low SNR"),
                ("12", "DATAC3", "126 B", "Payload; low SNR (~0 dB)"),
                ("10", "DATAC1", "510 B", "Payload; +5 dB SNR"),
                ("24", "DATAC17", "1180 B", "Payload; intermediate SNR (~+8 dB)"),
                ("25", "QAM16C2", "1213 B", "Payload; high SNR (~+15 dB)"),
                ("23", "DATAC16", "14 B", "Control; ARQ control channel"),
            ),
        )

    def test_exact_and_human_byte_format(self):
        self.assertEqual(format_bytes(9679), "9679 B (9.45 KiB)")
        self.assertEqual(format_bytes(110), "110 B")
        self.assertEqual(format_bytes(9789), "9789 B (9.56 KiB)")

    def test_version(self):
        self.assertEqual(__version__, "0.2.2")

    def test_legacy_text_is_ignored(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
            fh.write("11:35:49.509 [+59.596s] [INF] old text log\n")
            path = Path(fh.name)
        try:
            self.assertEqual(parse_file(path), [])
        finally:
            path.unlink(missing_ok=True)

    def test_malformed_json_is_ignored(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
            fh.write("not-json\n")
            path = Path(fh.name)
        try:
            self.assertEqual(parse_file(path), [])
        finally:
            path.unlink(missing_ok=True)

    def test_invalid_records_are_ignored(self):
        lines = [
            '[]\n',
            '{"m":"missing timestamp"}\n',
            '{"t":1788223495821}\n',
            '{"t":"bad","m":"bad timestamp"}\n',
        ]
        from parser import parse_json_lines
        self.assertEqual(parse_json_lines(lines), [])

    def test_corrupt_line_does_not_invalidate_session(self):
        lines = [
            '{"t":1788223495821,"up":37152,"lv":"INF","c":"tcp-ctl","m":"Command received: CONNECT KT7RUN KO0OOO"}\n',
            '{"t":1788223515604,"up":56935,"lv":"INF","c":"arq","m":"Connected to KO0OOO"}\n',
            '{"t":1788223515604,"up":56935,"lv":"TMG","c":"arq-timing","m":"connect mode=DATAC16"}\n',
            '{"t":1788223604998,"up":146329,"lv":"INF","c":"radio","m":"TX enabled (PTT ON)\n',
            '{"t":1788223729345,"up":270676,"lv":"INF","c":"arq","m":"Disconnected"}\n',
            '{"t":1788223729345,"up":270676,"lv":"TMG","c":"arq-timing","m":"disconnect reason=peer_ack tx_bytes=107 rx_bytes=1718 frames_tx=7 frames_rx=7 retries=1"}\n',
        ]
        from parser import parse_json_lines
        sessions = parse_json_lines(lines)
        self.assertEqual(len(sessions), 1)
        metrics = calculate_metrics(sessions[0])
        self.assertEqual(metrics.result, "DISCONNECTED (peer_ack)")
        self.assertEqual(metrics.tx_bytes, 107)
        self.assertEqual(metrics.rx_bytes, 1718)
        self.assertEqual(metrics.frames_tx, 7)
        self.assertEqual(metrics.frames_rx, 7)
        self.assertEqual(metrics.retries, 1)


class ReceiveOnlySessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = parse_file(ROOT / "tests" / "sample_receive.json")
        cls.session = cls.sessions[0]
        cls.metrics = calculate_metrics(cls.session)

    def test_receive_session_detected(self):
        self.assertEqual(len(self.sessions), 1)

    def test_receive_callsigns(self):
        self.assertEqual(self.session.mycall, "KT7RUN")
        self.assertEqual(self.session.peer, "KT7RUN-2")

    def test_receive_session_start(self):
        self.assertEqual(
            self.session.start,
            parse_json_timestamp(1788218178229),
        )

    def test_receive_setup_time(self):
        self.assertAlmostEqual(self.metrics.setup_seconds, 8.739, places=3)

    def test_receive_session_end(self):
        self.assertEqual(
            self.session.end,
            parse_json_timestamp(1788218259330),
        )
        self.assertAlmostEqual(self.session.duration_seconds, 81.101, places=3)

    def test_receive_counters(self):
        self.assertEqual(self.metrics.tx_bytes, 103)
        self.assertEqual(self.metrics.rx_bytes, 67)
        self.assertEqual(self.metrics.total_bytes, 170)
        self.assertEqual(self.metrics.frames_tx, 3)
        self.assertEqual(self.metrics.frames_rx, 2)
        self.assertEqual(self.metrics.retries, 0)

    def test_receive_modes(self):
        self.assertEqual(self.metrics.connect_mode, "DATAC16")
        self.assertEqual(
            self.metrics.payload_transitions,
            ["DATAC15 → DATAC3"],
        )
        self.assertEqual(
            self.metrics.peer_tx_requested_transitions,
            ["DATAC15 → DATAC3"],
        )
        self.assertEqual(self.metrics.final_tx_mode, "DATAC3")

    def test_receive_result(self):
        self.assertEqual(self.metrics.result, "DISCONNECTED (rx_disconnect)")


class SummaryAfterDisconnectedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = parse_file(
            ROOT / "tests" / "sample_summary_after_disconnect.json"
        )
        cls.session = cls.sessions[0]
        cls.metrics = calculate_metrics(cls.session)

    def test_summary_after_disconnected_is_retained(self):
        self.assertEqual(len(self.sessions), 1)
        self.assertEqual(self.metrics.disconnect_reason, "peer_ack")
        self.assertEqual(self.metrics.result, "DISCONNECTED (peer_ack)")
        self.assertEqual(self.metrics.tx_bytes, 107)
        self.assertEqual(self.metrics.rx_bytes, 1718)
        self.assertEqual(self.metrics.frames_tx, 7)
        self.assertEqual(self.metrics.frames_rx, 7)
        self.assertEqual(self.metrics.retries, 1)

    def test_disconnected_timestamp_remains_session_end(self):
        self.assertEqual(
            self.session.end,
            parse_json_timestamp(1788223729345),
        )


if __name__ == "__main__":
    unittest.main()
