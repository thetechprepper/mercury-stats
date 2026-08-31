import sys
import tempfile
import unittest
from datetime import timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parser import MercuryLogError, parse_file, parse_json_timestamp


class JsonParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = parse_file(ROOT / "tests" / "sample.json")

    def test_json_session_count(self):
        self.assertEqual(len(self.sessions), 1)

    def test_json_peer(self):
        self.assertEqual(self.sessions[0].peer, "KO0OOO")

    def test_json_disconnect_closes_session(self):
        self.assertEqual(self.sessions[0].result, "DISCONNECTED")

    def test_json_timestamp_uses_epoch_date(self):
        start = self.sessions[0].start
        self.assertEqual(start.tzinfo, timezone.utc)
        self.assertEqual(start.year, 2026)
        self.assertEqual(start.month, 8)
        self.assertEqual(start.day, 31)
        self.assertEqual(start.hour, 17)
        self.assertEqual(start.minute, 57)
        self.assertEqual(start.second, 8)
        self.assertEqual(start.microsecond, 500000)

    def test_json_duration(self):
        self.assertAlmostEqual(self.sessions[0].duration_seconds, 59.398, places=3)

    def test_epoch_conversion(self):
        dt = parse_json_timestamp(1788198961579)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 31)
        self.assertEqual(dt.hour, 17)
        self.assertEqual(dt.minute, 56)
        self.assertEqual(dt.second, 1)
        self.assertEqual(dt.microsecond, 579000)

    def test_legacy_text_log_is_rejected(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
            fh.write(
                "11:38:01.593 [+0.000s] [INF] [main] "
                "Async logger initialized\\n"
            )
            temp_path = Path(fh.name)

        try:
            with self.assertRaises(MercuryLogError):
                parse_file(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def test_malformed_json_is_rejected(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
            fh.write('{"t":1788198961579,"m":"ok"}\\n')
            fh.write('not-json\\n')
            temp_path = Path(fh.name)

        try:
            with self.assertRaises(MercuryLogError):
                parse_file(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
