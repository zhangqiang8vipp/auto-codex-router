import json
import os
import tempfile
import unittest

import web_panel


class WebPanelTests(unittest.TestCase):
    def test_panel_is_offline_and_bilingual(self):
        html = web_panel.PANEL_HTML
        self.assertIn("<title>", html)
        self.assertIn("Auto Codex Router", html)
        # bilingual brand present
        self.assertIn("自动 Codex 路由", html)
        # key controls/endpoints
        self.assertIn('id="autoSwitch"', html)
        self.assertIn("/control/status", html)
        self.assertIn("/control/auto", html)
        self.assertIn("/control/recent", html)
        # no external CDN dependency -> works offline
        self.assertNotIn("https://cdn.", html)
        self.assertNotIn("http://localhost", html)

    def test_recent_records_parses_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "live.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                for i in range(40):
                    fh.write(json.dumps({
                        "at": f"2026-09-22T10:{i:02d}:00",
                        "model": "gpt-5.6-terra",
                        "effort": "low",
                        "route_source": "jev" if i % 5 == 0 else "lease",
                        "lease_reason": "new_user_turn",
                        "status": 200,
                        "step": "user_turn",
                        "task": "task " + str(i),
                    }) + "\n")
            rows = web_panel.recent_records(path, limit=10)
            self.assertEqual(len(rows), 10)
            self.assertEqual(rows[-1]["task"], "task 39")
            self.assertEqual(rows[0]["effort"], "low")

    def test_recent_records_missing_file(self):
        self.assertEqual(web_panel.recent_records("does-not-exist.jsonl"), [])

    def test_recent_skips_bad_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "live.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("not json\n")
                fh.write(json.dumps({"at": "x", "model": "m", "status": 200}) + "\n")
            rows = web_panel.recent_records(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["at"], "x")


if __name__ == "__main__":
    unittest.main()
