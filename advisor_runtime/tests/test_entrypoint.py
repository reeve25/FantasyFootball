import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ff_entry", ROOT / "ff.py")
ff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ff)


class EntrypointTests(unittest.TestCase):
    def test_status_makes_no_network_calls(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("network forbidden")):
            status = ff.local_status()
        self.assertEqual(status["network_calls"], 0)
        self.assertFalse(status["model_api_required"])

    def test_compact_preserves_trade_gates_and_provenance(self):
        raw = {"warnings": ["stale"], "source_freshness": {"fresh": False}, "involved_rosters": ["huge"], "exact_engine_decision_math": {"my_delta_pg": 1, "perspective_delta_pg": 1, "trade_validation": {"actionable": False}, "perspective_weekly_lineup_changes": [{"week": 3, "delta": 1}, {"week": 4, "delta": 2}]}}
        out = ff.compact(raw)
        self.assertEqual(out["warnings"], ["stale"])
        self.assertFalse(out["exact_engine_decision_math"]["trade_validation"]["actionable"])
        self.assertEqual(out["exact_engine_decision_math"]["first_effective_week_lineup_change"]["week"], 3)
        self.assertNotIn("my_delta_pg", out["exact_engine_decision_math"])

    def test_deadline_stops_worker_and_emits_valid_json(self):
        result = subprocess.run([sys.executable, str(ROOT / "ff.py"), "--timeout", "0.01", "packet", "Compare players", "--offline"], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        packet = json.loads(result.stdout)
        self.assertEqual(packet["run_status"], "deadline_reached")
        self.assertLess(packet["elapsed_seconds"], 3)

    def test_atomic_json_is_valid(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "evidence.json"
            ff.write_json(path, {"value": None})
            self.assertEqual(json.loads(path.read_text()), {"value": None})


if __name__ == "__main__":
    unittest.main()
