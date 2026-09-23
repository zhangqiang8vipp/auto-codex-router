import os
import tempfile
import unittest

import model_roster
from routing_policy import (ASTRA, DEFAULT_ALLOW, GENERAL_ORDER, LUNA, SOL,
                           TERRA)

# A catalog containing every known model.
ALL_SLUGS = list(GENERAL_ORDER) + ["gpt-daybreak-blue-latest",
                                   "codex-auto-review",
                                   "gpt-daybreak-red-latest", "gpt-reserve"]


class ModelRosterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_defaults_gpt6_allow_others_deny(self):
        roster = model_roster.load(self.state)
        for model in DEFAULT_ALLOW:
            self.assertEqual(roster[model], "allow")
            self.assertTrue(model_roster.is_allowed(model, state_dir=self.state))
        self.assertEqual(model_roster.state_for("gpt-daybreak-blue-latest",
                                                state_dir=self.state), "deny")
        gen, special = model_roster.candidate_sets(ALL_SLUGS, state_dir=self.state)
        self.assertEqual(gen, [LUNA, SOL, ASTRA])
        self.assertEqual(special, [])

    def test_catalog_intersection_excludes_absent_even_if_allowed(self):
        # Terra defaults to deny; explicitly allow it, then omit it from catalog.
        model_roster.set_state(self.state, TERRA, "allow")
        gen, _ = model_roster.candidate_sets(
            [LUNA, SOL, ASTRA], state_dir=self.state)
        self.assertNotIn(TERRA, gen)

    def test_persist_and_restore_default(self):
        model_roster.set_state(self.state, SOL, "deny")
        self.assertTrue(os.path.exists(model_roster._path(self.state)))
        gen, _ = model_roster.candidate_sets(ALL_SLUGS, state_dir=self.state)
        self.assertEqual(gen, [LUNA, ASTRA])
        # restoring the default removes the explicit override
        model_roster.set_state(self.state, SOL, "allow")
        self.assertEqual(model_roster.load_overrides(self.state), {})

    def test_enforce_keeps_candidate(self):
        self.assertEqual(model_roster.enforce(SOL, "high", [LUNA, SOL, ASTRA]),
                         (SOL, "high"))

    def test_enforce_denied_prefers_higher(self):
        # middle (SOL) denied -> next higher allowed is ASTRA, effort preserved
        self.assertEqual(model_roster.enforce(SOL, "low", [LUNA, ASTRA]),
                         (ASTRA, "low"))

    def test_enforce_denied_top_falls_lower(self):
        self.assertEqual(model_roster.enforce(ASTRA, "high", [LUNA, SOL]),
                         (SOL, "high"))

    def test_all_denied_returns_none(self):
        self.assertIsNone(model_roster.enforce(LUNA, "low", []))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            model_roster.set_state(self.state, LUNA, "maybe")
        with self.assertRaises(ValueError):
            model_roster.set_state(self.state, "", "allow")


if __name__ == "__main__":
    unittest.main()
