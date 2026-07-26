"""Contraction during a live execution, not just at the planner.

Step 2 proved the planner narrows when given an improved confidence profile.
These tests cover the orchestrator actually reaching that state mid-run:
cancelling pending work, preserving completed work, and recording the
direction of every plan revision.
"""

from pathlib import Path
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator


ROOT = Path(__file__).resolve().parent

STABLE = "SCN-PAY-001"
CONTRADICTION = "SCN-PAY-CONTRADICT-001"
RESOLVED = "SCN-PAY-RESOLVED-001"


def execute(scenario_id: str):
    return AdaptiveExecutionOrchestrator(ROOT).execute(
        correlation_id=f"TEST-{scenario_id}",
        scenario_id=scenario_id,
    )


class FrozenScenarioTests(unittest.TestCase):
    """The two V1 demonstration scenarios must not shift."""

    def test_stable_scenario_never_revises_its_plan(self):
        assessment = execute(STABLE)
        self.assertEqual(assessment.plan_transitions, [])
        self.assertFalse(assessment.expanded_during_execution)
        self.assertFalse(assessment.contracted_during_execution)
        self.assertEqual(
             assessment.final_confidence_score, assessment.initial_confidence_score
         )
        self.assertEqual(assessment.final_agent_count, 3)

    def test_contradiction_scenario_expands_and_stays_expanded(self):
        assessment = execute(CONTRADICTION)
        self.assertTrue(assessment.expanded_during_execution)
        self.assertFalse(assessment.contracted_during_execution)
        self.assertLess(
             assessment.final_confidence_score, assessment.initial_confidence_score
         )
        self.assertEqual(assessment.final_plan_mode, "FULL_INVESTIGATION")
        self.assertEqual(assessment.final_agent_count, 6)
        self.assertEqual(len(assessment.plan_transitions), 1)
        self.assertEqual(
            assessment.plan_transitions[0].direction,
            "EXPANSION",
        )


class LiveContractionTests(unittest.TestCase):
    def test_resolved_scenario_expands_then_contracts(self):
        assessment = execute(RESOLVED)
        self.assertTrue(assessment.expanded_during_execution)
        self.assertTrue(assessment.contracted_during_execution)

        directions = [t.direction for t in assessment.plan_transitions]
        self.assertEqual(directions, ["EXPANSION", "CONTRACTION"])

        modes = [
            assessment.plan_transitions[0].from_mode,
            assessment.plan_transitions[0].to_mode,
            assessment.plan_transitions[1].to_mode,
        ]
        self.assertEqual(
            modes,
            [
                "ACCELERATED_VALIDATION",
                "FULL_INVESTIGATION",
                "ACCELERATED_VALIDATION",
            ],
        )

    def test_contraction_cancels_pending_work_without_executing_it(self):
        assessment = execute(RESOLVED)
        contraction = assessment.plan_transitions[1]

        self.assertIn(
            "evidence_fusion_recommendation",
            contraction.cancelled_skills,
        )
        self.assertNotIn(
            "evidence_fusion_recommendation",
            assessment.completed_skills,
        )
        self.assertNotIn(
            "evidence_fusion_recommendation",
            assessment.skill_outputs,
        )

    def test_contraction_preserves_every_completed_skill(self):
        assessment = execute(RESOLVED)
        contraction = assessment.plan_transitions[1]

        # Everything finished before the revision is retained, including the
        # deep-investigation skills the narrower plan no longer requires.
        for skill in (
            "semantic_context",
            "due_diligence_validation",
            "detailed_telemetry_analysis",
            "governed_knowledge_retrieval",
            "change_dependency_investigation",
        ):
            self.assertIn(skill, contraction.completed_skills_retained)
            self.assertIn(skill, assessment.completed_skills)
            self.assertIn(skill, assessment.skill_outputs)

    def test_cancelled_skill_is_never_also_a_completed_skill(self):
        for scenario in (STABLE, CONTRADICTION, RESOLVED):
            assessment = execute(scenario)
            for transition in assessment.plan_transitions:
                for skill in transition.cancelled_skills:
                    self.assertNotIn(
                        skill,
                        transition.completed_skills_retained,
                        f"{scenario}: {skill} was both cancelled and retained.",
                    )

    def test_contraction_substitutes_the_recommendation_skill(self):
        assessment = execute(RESOLVED)
        # The narrower plan supplies its own recommendation skill in place of
        # the cancelled fusion step.
        self.assertIn("governed_recommendation", assessment.completed_skills)
        self.assertIn(
            "governed_recommendation",
            assessment.plan_transitions[1].added_skills,
        )
        self.assertTrue(assessment.recommendation)

    def test_recovery_does_not_restore_original_confidence(self):
        assessment = execute(RESOLVED)
        self.assertLess(
            assessment.final_confidence_score,
            assessment.initial_confidence_score,
        )
        self.assertEqual(assessment.final_confidence_level, "HIGH")

    def test_human_approval_is_enforced_in_every_scenario(self):
        for scenario in (STABLE, CONTRADICTION, RESOLVED):
            assessment = execute(scenario)
            self.assertTrue(
                assessment.automation_readiness["human_approval_enforced"],
                f"{scenario} did not enforce human approval.",
            )


class ReassessmentRecordTests(unittest.TestCase):
    def test_each_hook_skill_records_its_own_reassessment(self):
        assessment = execute(RESOLVED)
        reassessments = assessment.skill_outputs["confidence_reassessments"]
        self.assertEqual(
            sorted(reassessments),
            ["change_dependency_investigation", "due_diligence_validation"],
        )

    def test_unkeyed_reassessment_stays_bound_to_the_first_hook(self):
        """Existing consumers read the single key; it must not be overwritten."""
        assessment = execute(RESOLVED)
        first = assessment.skill_outputs["confidence_reassessment"]
        keyed = assessment.skill_outputs["confidence_reassessments"]
        self.assertEqual(first, keyed["due_diligence_validation"])

    def test_second_reassessment_restores_rather_than_erodes(self):
        assessment = execute(RESOLVED)
        second = assessment.skill_outputs["confidence_reassessments"][
            "change_dependency_investigation"
        ]
        self.assertGreater(
            second["updated_confidence_score"],
            second["initial_confidence_score"],
        )
        self.assertEqual(
            second["resolved_hard_flags"],
            ["CREDIBLE_KNOWLEDGE_CONTRADICTION"],
        )
        self.assertFalse(second["credit_blocked_by_hard_flags"])


if __name__ == "__main__":
    unittest.main()
