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
            _model("x-custom-thing"),
        ]}
        with open(os.path.join(state, "merged-models.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(catalog, fh)

    def test_build_groups_models_by_order(self):
        with tempfile.TemporaryDirectory() as state:
            self._write(state)
            data = panel_data.build(state, True)
            groups = {g["tier"]: g for g in data["execution"]}
            # Known general models are ordered by the master general order.
            general_slugs = [m["slug"] for m in groups["general"]["models"]]
            self.assertEqual(
                general_slugs,
                ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.5"])
            # Unknown models join the special bucket.
            self.assertEqual(groups["special"]["models"][0]["slug"],
                             "x-custom-thing")
            # These older models default to the blacklist -> not selectable.
            luna = groups["general"]["models"][0]
            self.assertFalse(luna["selectable"])
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
            # No catalog means no active ladder and no tier cards.
            self.assertEqual(len(data["tiers"]), 0)
            self.assertEqual(len(data["efforts"]), 5)


if __name__ == "__main__":
    unittest.main()
