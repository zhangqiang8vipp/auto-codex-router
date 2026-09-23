import os
import tempfile
import unittest

import model_roster
from routing_policy import ASTRA, LUNA, SOL, TERRA, TIERS


class ModelRosterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_defaults_tiers_allow_others_deny(self):
        roster = model_roster.load(self.state)
        for tier in TIERS:
            self.assertEqual(roster[tier], "allow")
            self.assertTrue(model_roster.is_allowed(tier, state_dir=self.state))
        self.assertEqual(model_roster.state_for("gpt-daybreak-blue-latest",
                                                state_dir=self.state), "deny")
        self.assertEqual(model_roster.allowed_tiers(state_dir=self.state), list(TIERS))

    def test_persist_and_restore_default(self):
        model_roster.set_state(self.state, TERRA, "deny")
        self.assertTrue(os.path.exists(model_roster._path(self.state)))
        self.assertEqual(model_roster.allowed_tiers(state_dir=self.state),
                         [LUNA, SOL, ASTRA])
        # restoring the default removes the explicit override
        model_roster.set_state(self.state, TERRA, "allow")
        self.assertEqual(model_roster.load_overrides(self.state), {})

    def test_enforce_keeps_allowed(self):
        self.assertEqual(model_roster.enforce(SOL, "high", state_dir=self.state),
                         (SOL, "high"))

    def test_enforce_denied_prefers_higher(self):
        model_roster.set_state(self.state, TERRA, "deny")
        # denied terra -> next higher allowed is sol, effort preserved
        self.assertEqual(model_roster.enforce(TERRA, "low", state_dir=self.state),
                         (SOL, "low"))

    def test_enforce_denied_falls_lower_when_no_higher(self):
        model_roster.set_state(self.state, ASTRA, "deny")
        self.assertEqual(model_roster.enforce(ASTRA, "high", state_dir=self.state),
                         (SOL, "high"))

    def test_enforce_all_denied_returns_none(self):
        for tier in TIERS:
            model_roster.set_state(self.state, tier, "deny")
        self.assertIsNone(model_roster.enforce(LUNA, "low", state_dir=self.state))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            model_roster.set_state(self.state, LUNA, "maybe")
        with self.assertRaises(ValueError):
            model_roster.set_state(self.state, "", "allow")


if __name__ == "__main__":
    unittest.main()
