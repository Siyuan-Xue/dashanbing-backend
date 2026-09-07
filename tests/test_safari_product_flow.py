"""Offline step-runner tests only; never starts Safari or reads credentials."""
import unittest
from scripts.verify_safari_product_flow import run_steps


class StepTests(unittest.TestCase):
    def test_failure_stops_flow_and_never_leaks_exception_text(self):
        visited, records = [], []
        def first():
            visited.append("first")
            return {"count": 5}
        def fail():
            visited.append("fail")
            raise RuntimeError("synthetic-private-token-response")
        result = run_steps([("first", first), ("fail", fail),
                            ("never", lambda: visited.append("never"))], records)
        self.assertFalse(result)
        self.assertEqual(visited, ["first", "fail"])
        self.assertEqual(records[0]["details"], {"count": 5})
        self.assertEqual(records[1]["error"], "unexpected_error")
        self.assertNotIn("synthetic-private-token", str(records))

    def test_success_is_once_per_step_and_timing_has_no_pass_threshold(self):
        visited, records = [], []
        def action():
            visited.append("clicked")
            return {"count": 4}
        self.assertTrue(run_steps([("select", action)], records))
        self.assertEqual(visited, ["clicked"])
        self.assertEqual(records[0]["status"], "matched")
        self.assertGreaterEqual(records[0]["elapsed_ms"], 0)


if __name__ == "__main__":
    unittest.main()
