import os
import tempfile
import unittest

import counters


class DailyCounters(unittest.TestCase):
    def test_classifies_route_sources(self):
        with tempfile.TemporaryDirectory() as d:
            c = counters.DailyCounters(os.path.join(d, "counters.json"))
            c.record("jev", "miss")
            c.record("jev", "exact")
            c.record("lease")
            c.record("lease")
            c.record("lease_escalation")
            c.record("fallback")
            t = c.today()
            self.assertEqual(t["total"], 6)
            self.assertEqual(t["jev_decisions"], 2)
            self.assertEqual(t["jev_cache_hits"], 1)
            self.assertEqual(t["lease_keep"], 2)
            self.assertEqual(t["local_escalations"], 1)
            self.assertEqual(t["fallbacks"], 1)
            # 4 of 6 calls avoided a fresh Jev decision
            self.assertEqual(t["jev_saved"], 4)

    def test_persists_and_reloads(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "counters.json")
            counters.DailyCounters(path).record("lease")
            counters.DailyCounters(path).record("lease")
            t = counters.DailyCounters(path).today()
            self.assertEqual(t["total"], 2)
            self.assertEqual(t["lease_keep"], 2)

    def test_empty_day_derived_fields(self):
        with tempfile.TemporaryDirectory() as d:
            t = counters.DailyCounters(os.path.join(d, "c.json")).today()
            self.assertEqual(t["total"], 0)
            self.assertEqual(t["jev_saved"], 0)
            self.assertEqual(t["keep_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
