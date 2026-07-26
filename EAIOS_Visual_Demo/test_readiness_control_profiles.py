"""Every remediation a scenario can propose must be described.

The readiness evaluator treats a missing control profile as failure: absent a
profile, reversibility, blast radius, and policy candidacy all report as
blocked. That is silent and misleading, because the action may be perfectly
reversible and simply undescribed. These tests make the omission loud.
"""

from pathlib import Path
import json
import unittest

from automation_readiness import AutomationReadinessEvaluator
from operational_confidence_engine import OperationalConfidenceEngine


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
POLICY_FILE = CONFIG / "automation_readiness_policy.json"


def policy() -> dict:
    return json.loads(POLICY_FILE.read_text(encoding="utf-8"))


def engine() -> OperationalConfidenceEngine:
    return OperationalConfidenceEngine(ROOT / "json", CONFIG / "confidence_policy.json")


def scenario_ids() -> list[str]:
    rows = json.loads((ROOT / "json" / "scenarios.json").read_text(encoding="utf-8"))
    return [row["scenario_id"] for row in rows]


def evaluate(scenario_id: str):
    """Readiness as judged at assessment time, before any evidence is gathered."""
    e = engine()
    return AutomationReadinessEvaluator(POLICY_FILE).evaluate(e.assess(scenario_id))


_executed: dict = {}


def executed_readiness(scenario_id: str) -> dict:
    """Readiness after the run, which is what the demonstration reports.

    Confidence can move during execution, so the two views legitimately
    differ: the cross-platform scenario is below the confidence threshold at
    assessment time and above it once vendor evidence lands.
    """
    if scenario_id not in _executed:
        from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator

        _executed[scenario_id] = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id=f"TEST-{scenario_id}",
            scenario_id=scenario_id,
        ).automation_readiness
    return _executed[scenario_id]


class ProfileCoverageTests(unittest.TestCase):
    def test_every_reachable_known_error_is_described_or_exempt(self):
        described = set(policy()["control_profiles"])
        exempt = set(policy().get("automation_exempt_known_errors", {}))
        suspended = set(policy()["suspension_hard_flags"])
        e = engine()
        for scenario_id in scenario_ids():
            assessment = e.assess(scenario_id)
            known_error = assessment.selected_known_error_id
            if known_error is None:
                continue
            if suspended & set(assessment.hard_flags):
                # Readiness is already suspended for a stated governance
                # reason. This test guards against readiness being blocked
                # merely because nobody described the action, which is the
                # opposite situation.
                continue
            with self.subTest(scenario=scenario_id, known_error=known_error):
                self.assertIn(
                    known_error,
                    described | exempt,
                    f"{known_error} is reachable from {scenario_id} but has neither a "
                    f"control profile nor an explicit automation exemption, so readiness "
                    f"will report reversibility, blast radius, and policy as blocked "
                    f"purely because the action was never described.",
                )

    def test_an_exemption_must_state_a_reason(self):
        for known_error, reason in policy().get(
            "automation_exempt_known_errors", {}
        ).items():
            with self.subTest(known_error=known_error):
                self.assertTrue(str(reason).strip())

    def test_a_known_error_is_never_both_described_and_exempt(self):
        described = set(policy()["control_profiles"])
        exempt = set(policy().get("automation_exempt_known_errors", {}))
        self.assertEqual(described & exempt, set())

    def test_every_profile_declares_the_controls_it_requires(self):
        for known_error, profile in policy()["control_profiles"].items():
            with self.subTest(known_error=known_error):
                self.assertTrue(
                    profile.get("required_constraints"),
                    f"{known_error} allows candidacy without naming any control.",
                )


class GatewayProfileTests(unittest.TestCase):
    def test_the_rollback_is_described_as_reversible_and_bounded(self):
        profile = policy()["control_profiles"]["KE-GATEWAY-001"]
        self.assertTrue(profile["reversible"])
        self.assertTrue(profile["bounded_blast_radius"])
        self.assertEqual(profile["blast_radius_scope"], "CROSS_PLATFORM_BOUNDED")

    def test_a_successful_history_does_not_authorise_autonomy(self):
        profile = policy()["control_profiles"]["KE-GATEWAY-001"]
        self.assertFalse(profile["autonomous_execution_permitted"])

    def test_the_required_controls_include_cross_platform_verification(self):
        readiness = executed_readiness("SCN-CROSS-GATEWAY-001")
        self.assertEqual(
            readiness["required_constraints"],
            [
                "ONE_GATEWAY_POLICY_AT_A_TIME",
                "CROSS_PLATFORM_VERIFICATION",
                "HUMAN_APPROVAL_IN_V1",
            ],
        )

    def test_describing_the_action_removes_only_the_phantom_blockers(self):
        for readiness in (
            executed_readiness("SCN-CROSS-GATEWAY-001")["blockers"],
            evaluate("SCN-CROSS-GATEWAY-001").blockers,
        ):
            for cleared in ("REVERSIBLE", "BOUNDED_BLAST_RADIUS", "POLICY"):
                self.assertNotIn(cleared, readiness)

    def test_real_outcome_evidence_still_blocks_candidacy(self):
        """The profile describes the action; it does not vouch for the record."""
        readiness = executed_readiness("SCN-CROSS-GATEWAY-001")
        self.assertEqual(
            readiness["blockers"], ["CONFIDENCE", "RECENT_SUCCESS", "RECURRENCE"]
        )
        self.assertNotEqual(readiness["status"], "CANDIDATE")
        self.assertEqual(readiness["status"], "BUILDING_EVIDENCE")

    def test_human_approval_survives_a_complete_control_profile(self):
        readiness = executed_readiness("SCN-CROSS-GATEWAY-001")
        self.assertTrue(readiness["human_approval_enforced"])
        self.assertTrue(readiness["advisory_only"])

    def test_confidence_buys_depth_but_never_permission(self):
        """The principle, in one scenario, in numbers.

        Recovered confidence clears the HIGH band, so the plan is allowed to
        narrow. It does not clear the automation-readiness bar, so nothing may
        run unattended. Depth changed; permission did not.
        """
        from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator

        run = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id="TEST-DEPTH-NOT-PERMISSION",
            scenario_id="SCN-CROSS-GATEWAY-001",
        )
        levels = json.loads(
            (CONFIG / "confidence_policy.json").read_text(encoding="utf-8")
        )["levels"]
        threshold = json.loads(
            (CONFIG / "automation_readiness_policy.json").read_text(encoding="utf-8")
        )["thresholds"]["minimum_confidence_score"]

        # Sufficient for depth: clears HIGH, so the plan contracts.
        self.assertGreaterEqual(run.final_confidence_score, float(levels["HIGH"]))
        self.assertTrue(run.contracted_during_execution)

        # Insufficient for permission: below the readiness bar, and blocked.
        self.assertLess(run.final_confidence_score, float(threshold))
        self.assertIn("CONFIDENCE", run.automation_readiness["blockers"])
        self.assertTrue(run.automation_readiness["human_approval_enforced"])


class ExistingReadinessUnchangedTests(unittest.TestCase):
    def test_v1_readiness_outcomes_are_untouched(self):
        for scenario_id, expected in (
            ("SCN-PAY-001", "CANDIDATE"),
            ("SCN-QUEUE-001", "SUSPENDED"),
        ):
            with self.subTest(scenario=scenario_id):
                self.assertEqual(evaluate(scenario_id).status, expected)


if __name__ == "__main__":
    unittest.main()
