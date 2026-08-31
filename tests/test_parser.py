import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from metrics import calculate_metrics
from parser import parse_file


class ParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = parse_file(
            ROOT / "tests" / "sample.log"
        )

    def test_session_count(self):
        self.assertEqual(len(self.sessions), 2)

    def test_first_peer(self):
        self.assertEqual(self.sessions[0].peer, "KO0OOO")

    def test_first_result(self):
        self.assertEqual(self.sessions[0].result, "SUCCESS")

    def test_second_result(self):
        self.assertEqual(self.sessions[1].result, "FAILED")

    def test_first_metrics(self):
        metrics = calculate_metrics(self.sessions[0])
        self.assertEqual(metrics.retries, 1)
        self.assertEqual(metrics.mode_upgrades, 1)
        self.assertEqual(metrics.bytes_seen, 636)
        self.assertEqual(metrics.initial_mode, "DATAC3")
        self.assertEqual(metrics.final_mode, "DATAC4")
        self.assertAlmostEqual(metrics.setup_seconds, 8.4, places=1)


if __name__ == "__main__":
    unittest.main()
