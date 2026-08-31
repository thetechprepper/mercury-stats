import sys
import tempfile
import unittest
from datetime import timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from metrics import ARQ_MODE_LEGEND, FREEDV_MODE_NAMES, calculate_metrics, format_bytes, mode_name
from parser import MercuryLogError, parse_file, parse_json_timestamp


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
                ("22", "DATAC15", "22 B", "Payload; lowest SNR / ladder floor"),
                ("18", "DATAC4", "46 B", "Payload; low SNR"),
                ("12", "DATAC3", "118 B", "Payload; default startup mode"),
                ("10", "DATAC1", "502 B", "Payload; +5 dB SNR"),
                ("24", "DATAC17", "1172 B", "Payload; intermediate SNR (~+8 dB)"),
                ("25", "QAM16C2", "1205 B", "Payload; high SNR (~+15 dB)"),
                ("23", "DATAC16", "6 B", "Control; ARQ control channel"),
            ),
        )

    def test_exact_and_human_byte_format(self):
        self.assertEqual(format_bytes(9679), "9679 B (9.45 KiB)")
        self.assertEqual(format_bytes(110), "110 B")
        self.assertEqual(format_bytes(9789), "9789 B (9.56 KiB)")

    def test_legacy_text_is_rejected(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
            fh.write("11:35:49.509 [+59.596s] [INF] old text log\n")
            path = Path(fh.name)
        try:
            with self.assertRaises(MercuryLogError):
                parse_file(path)
        finally:
            path.unlink(missing_ok=True)

    def test_malformed_json_is_rejected(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
            fh.write("not-json\n")
            path = Path(fh.name)
        try:
            with self.assertRaises(MercuryLogError):
                parse_file(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
