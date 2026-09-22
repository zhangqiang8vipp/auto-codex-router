import json
import os
import tempfile
import unittest

import panel_data


def _model(slug, default="medium", efforts=None, visibility="list"):
    efforts = efforts or ["low", "medium", "high"]
    return {
        "slug": slug,
        "display_name": slug.upper(),
        "description": slug + " description",
        "default_reasoning_level": default,
        "supported_reasoning_levels": [
            {"effort": e, "description": e + " desc"} for e in efforts],
        "visibility": visibility,
        "supported_in_api": True,
    }


class PanelDataTests(unittest.TestCase):
    def _write(self, state):
        catalog = {"models": [
            _model("gpt-5.6-luna"),
            _model("gpt-5.6-terra"),
            _model("gpt-5.5", default="xhigh", visibility="hide"),
        ]}
        with open(os.path.join(state, "merged-models.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(catalog, fh)

    def test_build_groups_models_by_tier(self):
        with tempfile.TemporaryDirectory() as state:
            self._write(state)
            data = panel_data.build(state, True)
            groups = {g["tier"]: g for g in data["execution"]}
            self.assertEqual(groups["gpt-5.6-luna"]["models"][0]["slug"],
                             "gpt-5.6-luna")
            self.assertEqual(groups["gpt-5.6-terra"]["models"][0]["slug"],
                             "gpt-5.6-terra")
            self.assertEqual(groups["special"]["models"][0]["slug"], "gpt-5.5")
            # effort chips carry descriptions and the default is flagged later in UI.
            luna = groups["gpt-5.6-luna"]["models"][0]
            self.assertEqual(luna["default_effort"], "medium")
            self.assertEqual(luna["efforts"][0]["effort"], "low")

    def test_decision_and_key_status(self):
        with tempfile.TemporaryDirectory() as state:
            self._write(state)
            on = panel_data.build(state, True)
            self.assertTrue(on["decision"]["judge"]["key_configured"])
            keys = {k["kind"]: k for k in on["keys"]}
            self.assertTrue(keys["typesafe"]["configured"])
            self.assertFalse(keys["openrouter"]["configured"])
            self.assertEqual(keys["typesafe"]["layer"], "decision")
            off = panel_data.build(state, False)
            self.assertFalse(off["decision"]["judge"]["key_configured"])
            self.assertFalse(
                {k["kind"]: k for k in off["keys"]}["typesafe"]["configured"])

    def test_missing_catalog_is_non_fatal(self):
        with tempfile.TemporaryDirectory() as state:
            data = panel_data.build(state, False)
            self.assertEqual(
                sum(len(g["models"]) for g in data["execution"]), 0)
            self.assertEqual(len(data["tiers"]), 4)
            self.assertEqual(len(data["efforts"]), 5)


if __name__ == "__main__":
    unittest.main()
