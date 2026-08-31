import sys
import tempfile
import unittest
from datetime import timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from metrics import calculate_metrics
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
        dt = parse_json_timestamp(1788201349509)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_disconnect_command_does_not_end_session(self):
        self.assertEqual(
            self.session.end,
            parse_json_timestamp(1788201434071),
        )

    def test_duration(self):
        self.assertAlmostEqual(self.session.duration_seconds, 84.562, places=3)

    def test_setup_time(self):
        self.assertAlmostEqual(self.metrics.setup_seconds, 7.843, places=3)

    def test_disconnect_reason(self):
        self.assertEqual(self.metrics.disconnect_reason, "peer_ack")
        self.assertEqual(self.metrics.result, "DISCONNECTED (peer_ack)")

    def test_authoritative_byte_counters(self):
        self.assertEqual(self.metrics.tx_bytes, 67)
        self.assertEqual(self.metrics.rx_bytes, 105)
        self.assertEqual(self.metrics.total_bytes, 172)

    def test_authoritative_retry_counter(self):
        self.assertEqual(self.metrics.retries, 0)

    def test_frames(self):
        self.assertEqual(self.metrics.frames_tx, 2)
        self.assertEqual(self.metrics.frames_rx, 3)

    def test_modes_are_not_conflated(self):
        self.assertEqual(self.metrics.connect_mode, "DATAC16")
        self.assertEqual(self.metrics.payload_transitions, ["22 → 12"])
        self.assertEqual(self.metrics.final_tx_mode, "DATAC3")

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
