"""Moving the threshold must actually re-plan, and must not buy governance.

The demo claims the plan is a consequence of the evidence rather than a
setting. A control that only moved a displayed number would be a claim about
the architecture dressed as a demonstration of it, so what is asserted here is
that the real orchestrator ran and reached a different plan.

The second claim is the more important one. Lowering the bar must not grant a
shortcut to anything carrying a categorical flag, however generous the
threshold becomes.
"""

from pathlib import Path
import unittest

from threshold_explorer import (
    CONTROL_SCENARIOS,
    blocking_flags,
    replanned,
    run_at_thresholds,
    shipped_levels,
)


ROOT = Path(__file__).resolve().parent

_cache: dict = {}


def at(high: float, medium: float):
    key = (high, medium)
    if key not in _cache:
        _cache[key] = run_at_thresholds(ROOT, high=high, medium=medium)
    return _cache[key]


def shipped():
    levels = shipped_levels(ROOT)
    return at(float(levels["HIGH"]), float(levels["MEDIUM"]))


class RaisingTheBarCostsSpeedTests(unittest.TestCase):
    def test_a_demanding_threshold_removes_the_shortcut(self):
        """Even 49 recorded outcomes stop being enough at 0.99."""
        payment = next(
            row for row in at(0.99, 0.50) if row.scenario_id == "SCN-PAY-001"
        )
        self.assertGreater(payment.confidence, 0.9)
        self.assertEqual(payment.plan, "FULL_INVESTIGATION")

    def test_the_same_scenario_keeps_it_at_the_shipped_bands(self):
        payment = next(
            row for row in shipped() if row.scenario_id == "SCN-PAY-001"
        )
        self.assertEqual(payment.plan, "ACCELERATED_VALIDATION")

    def test_confidence_itself_does_not_move(self):
        """The evidence did not change; only what it buys did."""
        before = {row.scenario_id: row.confidence for row in shipped()}
        after = {row.scenario_id: row.confidence for row in at(0.99, 0.50)}
        self.assertEqual(before, after)

    def test_something_visibly_re_plans(self):
        """A control nobody can see working is worse than no control."""
        self.assertTrue(replanned(shipped(), at(0.99, 0.50)))


class LoweringTheBarBuysNothingTests(unittest.TestCase):
    """The governance claim, and the reason this panel is worth showing."""

    def test_a_permissive_threshold_grants_no_shortcut(self):
        generous = at(0.30, 0.10)
        for row in generous:
            if row.blocked_by:
                with self.subTest(scenario=row.scenario_id):
                    self.assertEqual(
                        row.plan,
                        "FULL_INVESTIGATION",
                        f"{row.scenario_id} cleared the band and was let "
                        f"through despite {row.blocked_by}",
                    )

    def test_no_flagged_scenario_becomes_an_automation_candidate(self):
        for row in at(0.30, 0.10):
            if row.blocked_by:
                with self.subTest(scenario=row.scenario_id):
                    self.assertNotEqual(row.readiness, "CANDIDATE")

    def test_the_generous_run_re_plans_nothing(self):
        self.assertEqual(replanned(shipped(), at(0.30, 0.10)), [])

    def test_a_flag_resolved_at_runtime_is_not_reported_as_blocking(self):
        """The gateway retires its high-risk-change flag mid-run and then
        accelerates. Reading the accumulated factors would caption an
        accelerated plan with the reason it was blocked."""
        gateway = next(
            row for row in shipped() if row.scenario_id == "SCN-CROSS-GATEWAY-001"
        )
        self.assertEqual(gateway.plan, "ACCELERATED_VALIDATION")
        self.assertEqual(gateway.blocked_by, ())

    def test_the_flags_are_read_from_policy_not_restated(self):
        flags = blocking_flags(ROOT)
        self.assertIn("EXPERIENCE_TRANSFERRED_NOT_DIRECT", flags)
        self.assertIn("HYPOTHESIS_FROM_DOCUMENTATION_ONLY", flags)
        source = (ROOT / "threshold_explorer.py").read_text(encoding="utf-8")
        self.assertNotIn('"RECENT_HIGH_RISK_CHANGE"', source)


class ThePanelUsesTheRealPipelineTests(unittest.TestCase):
    def test_the_app_does_not_hold_the_logic(self):
        """Pipeline logic in the presentation layer cannot be tested without
        a browser, and the browser is where it fails in front of people."""
        source = (ROOT / "eaios_story_app.py").read_text(encoding="utf-8")
        self.assertIn("from threshold_explorer import", source)
        self.assertNotIn("TemporaryDirectory() as directory:\n        root", source)

    def test_every_control_scenario_exists(self):
        import json

        known = {
            row["scenario_id"]
            for row in json.loads(
                (ROOT / "json" / "scenarios.json").read_text(encoding="utf-8")
            )
        }
        for scenario_id, _ in CONTROL_SCENARIOS:
            with self.subTest(scenario=scenario_id):
                self.assertIn(scenario_id, known)


if __name__ == "__main__":
    unittest.main()
