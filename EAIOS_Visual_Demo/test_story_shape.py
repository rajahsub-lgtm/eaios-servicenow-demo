"""The demonstration's shape, asserted independently of its numbers.

Pinning `0.898` tests the fixture, not the behaviour. It breaks whenever
evidence is added and says nothing about whether the story still holds. These
tests assert directions, orderings and invariants instead: confidence erodes
here, recovers but not fully there, plans widen then narrow, and approval is
never surrendered.

This is the contract the work on experience transfer must not break. The
values underneath it are free to move.
"""

from pathlib import Path
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator


ROOT = Path(__file__).resolve().parent

STABLE = "SCN-PAY-001"
CONTRADICTION = "SCN-PAY-CONTRADICT-001"
RESOLVED = "SCN-PAY-RESOLVED-001"
CROSS = "SCN-CROSS-GATEWAY-001"
ALL_SCENARIOS = (STABLE, CONTRADICTION, RESOLVED, CROSS)

_runs: dict = {}


def run(scenario_id: str):
    if scenario_id not in _runs:
        _runs[scenario_id] = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id=f"SHAPE-{scenario_id}", scenario_id=scenario_id
        )
    return _runs[scenario_id]


class HoldTests(unittest.TestCase):
    """Stable evidence: nothing moves, and the plan stays smallest."""

    def test_confidence_holds(self):
        assessment = run(STABLE)
        self.assertEqual(
            assessment.final_confidence_score, assessment.initial_confidence_score
        )

    def test_the_plan_is_never_revised(self):
        self.assertEqual(run(STABLE).plan_transitions, [])
        self.assertFalse(run(STABLE).expanded_during_execution)
        self.assertFalse(run(STABLE).contracted_during_execution)

    def test_it_uses_the_narrowest_plan_of_any_scenario(self):
        widths = {
            scenario: run(scenario).final_plan_agent_count
            for scenario in ALL_SCENARIOS
        }
        self.assertEqual(widths[STABLE], min(widths.values()))


class ErodeTests(unittest.TestCase):
    """Credible contradiction: confidence falls and the plan widens."""

    def test_confidence_erodes(self):
        assessment = run(CONTRADICTION)
        self.assertLess(
            assessment.final_confidence_score, assessment.initial_confidence_score
        )

    def test_the_plan_widens_and_stays_wide(self):
        assessment = run(CONTRADICTION)
        self.assertTrue(assessment.expanded_during_execution)
        self.assertFalse(assessment.contracted_during_execution)
        self.assertGreater(
            assessment.final_plan_agent_count, assessment.initial_plan_agent_count
        )

    def test_automation_is_suspended(self):
        self.assertEqual(run(CONTRADICTION).automation_readiness["status"], "SUSPENDED")


class RecoverTests(unittest.TestCase):
    """Resolution: confidence returns, but never all the way."""

    def test_confidence_recovers_from_its_low_point(self):
        assessment = run(RESOLVED)
        eroded = run(CONTRADICTION).final_confidence_score
        self.assertGreater(assessment.final_confidence_score, eroded)

    def test_recovery_is_never_complete(self):
        """The asymmetry, stated as a property rather than a number."""
        assessment = run(RESOLVED)
        self.assertLess(
            assessment.final_confidence_score, assessment.initial_confidence_score
        )

    def test_the_plan_widens_and_then_narrows(self):
        assessment = run(RESOLVED)
        self.assertTrue(assessment.expanded_during_execution)
        self.assertTrue(assessment.contracted_during_execution)
        directions = [t.direction for t in assessment.plan_transitions]
        self.assertEqual(directions, ["EXPANSION", "CONTRACTION"])

    def test_the_excursion_remains_visible_after_returning(self):
        assessment = run(RESOLVED)
        self.assertEqual(
            assessment.final_plan_agent_count, assessment.initial_plan_agent_count
        )
        self.assertGreater(
            assessment.peak_plan_agent_count, assessment.final_plan_agent_count
        )

    def test_more_agents_contributed_than_the_final_plan_needed(self):
        assessment = run(RESOLVED)
        self.assertGreater(
            assessment.unique_agents_executed, assessment.final_plan_agent_count
        )


class DiscoverTests(unittest.TestCase):
    """Cross-platform: starts wide, discovers the shared cause, narrows."""

    def test_it_starts_wide_and_narrows(self):
        assessment = run(CROSS)
        self.assertEqual(assessment.initial_plan_mode, "FULL_INVESTIGATION")
        self.assertTrue(assessment.contracted_during_execution)
        self.assertLess(
            assessment.final_plan_agent_count, assessment.initial_plan_agent_count
        )

    def test_confidence_rises_as_evidence_arrives(self):
        assessment = run(CROSS)
        self.assertGreater(
            assessment.final_confidence_score, assessment.initial_confidence_score
        )

    def test_the_second_platform_and_shared_cause_are_reached(self):
        entities = set(
            run(CROSS).skill_outputs["semantic_context"]["authoritative_entity_ids"]
        )
        for discovered in (
            "COMP-TEAMS-SIGNALING",
            "COMP-SECURE-WEB-GATEWAY",
            "COMP-GATEWAY-TLS-POLICY",
        ):
            with self.subTest(entity=discovered):
                self.assertIn(discovered, entities)

    def test_both_vendors_are_established_and_retired(self):
        vendor = run(CROSS).skill_outputs["external_service_health"]
        self.assertEqual(len(vendor["vendors_reporting_healthy"]), 2)
        self.assertEqual(len(vendor["eliminated_external_hypotheses"]), 2)

    def test_an_out_of_grant_request_is_refused(self):
        self.assertEqual(run(CROSS).policy_decision_counts.get("DENY"), 1)


class RelativeOrderingTests(unittest.TestCase):
    """The four scenarios must remain distinguishable from one another."""

    def test_stable_ends_most_confident_and_contradiction_least(self):
        finals = {s: run(s).final_confidence_score for s in ALL_SCENARIOS}
        self.assertEqual(max(finals, key=finals.get), STABLE)
        self.assertEqual(min(finals, key=finals.get), CONTRADICTION)

    def test_resolution_sits_between_erosion_and_stability(self):
        self.assertLess(
            run(CONTRADICTION).final_confidence_score,
            run(RESOLVED).final_confidence_score,
        )
        self.assertLess(
            run(RESOLVED).final_confidence_score, run(STABLE).final_confidence_score
        )

    def test_every_scenario_tells_a_different_story(self):
        shapes = {
            (
                run(s).expanded_during_execution,
                run(s).contracted_during_execution,
            )
            for s in ALL_SCENARIOS
        }
        self.assertEqual(len(shapes), 4, "two scenarios have the same plan shape")


class GovernanceInvariants(unittest.TestCase):
    """True in every scenario, whatever the evidence says."""

    def test_human_approval_is_never_surrendered(self):
        for scenario in ALL_SCENARIOS:
            with self.subTest(scenario=scenario):
                assessment = run(scenario)
                self.assertTrue(
                    assessment.automation_readiness["human_approval_enforced"]
                )
                self.assertEqual(assessment.safety_status, "REQUIRES_HUMAN_APPROVAL")

    def test_nothing_is_ever_reported_as_executed(self):
        for scenario in ALL_SCENARIOS:
            with self.subTest(scenario=scenario):
                self.assertNotIn(
                    run(scenario).approval_state.upper(), {"APPROVED", "AUTO_APPROVED"}
                )

    def test_confidence_stays_within_bounds(self):
        for scenario in ALL_SCENARIOS:
            with self.subTest(scenario=scenario):
                assessment = run(scenario)
                for score in (
                    assessment.initial_confidence_score,
                    assessment.final_confidence_score,
                ):
                    self.assertGreaterEqual(score, 0.0)
                    self.assertLessEqual(score, 1.0)

    def test_every_scenario_reaches_a_recommendation(self):
        for scenario in ALL_SCENARIOS:
            with self.subTest(scenario=scenario):
                self.assertTrue(run(scenario).recommendation)


if __name__ == "__main__":
    unittest.main()
