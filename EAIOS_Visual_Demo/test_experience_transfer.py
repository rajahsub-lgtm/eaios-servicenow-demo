"""Two answers the system could not previously give.

A presentation it has resolved fifty times elsewhere should be recognised —
and recognised *as an analogy*, which is weaker evidence than having treated
it here. A presentation nothing resembles should produce a governed account
of not knowing, not an exception.

The non-diagnosis case is now a component with neither recorded experience nor
written procedure. Where documentation exists, the system reads it instead;
that path is asserted in test_documented_reasoning.py.
"""

from pathlib import Path
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator


ROOT = Path(__file__).resolve().parent

DIRECT = "SCN-PAY-001"
SIBLING = "SCN-PAY-EU-001"
UNSEEN = "SCN-UNDOCUMENTED-001"
DOCUMENTED = "SCN-NOVEL-INDEX-001"

_runs: dict = {}


def run(scenario_id: str):
    if scenario_id not in _runs:
        _runs[scenario_id] = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id=f"TRANSFER-{scenario_id}", scenario_id=scenario_id
        )
    return _runs[scenario_id]


def leading_candidate(scenario_id: str):
    return run(scenario_id).skill_outputs and next(
        c
        for c in AdaptiveExecutionOrchestrator(ROOT)
        .confidence_engine.assess(scenario_id)
        .candidate_assessments
    )


class TransferredExperienceTests(unittest.TestCase):
    def test_a_sibling_component_inherits_recorded_experience(self):
        """Fifty cases next door are worth something. They were worth nothing."""
        assessment = run(SIBLING)
        self.assertGreater(assessment.initial_confidence_score, 0.5)
        self.assertEqual(
            assessment.recommendation["leading_hypothesis_id"], "KE-PAY-001"
        )

    def test_inherited_experience_is_worth_less_than_firsthand(self):
        self.assertLess(
            run(SIBLING).initial_confidence_score,
            run(DIRECT).initial_confidence_score,
        )

    def test_the_match_is_recorded_as_an_analogy(self):
        candidate = leading_candidate(SIBLING)
        self.assertEqual(candidate.experience_class, "TRANSFERRED")
        self.assertIn("STRUCTURAL_SIBLING", candidate.similarity_reasons)
        self.assertIn("TRANSFERRED_EXPERIENCE", candidate.similarity_reasons)

    def test_firsthand_experience_is_recorded_as_direct(self):
        candidate = leading_candidate(DIRECT)
        self.assertEqual(candidate.experience_class, "DIRECT")
        self.assertIn("DIRECT_EXPERIENCE", candidate.similarity_reasons)

    def test_an_analogy_never_earns_the_accelerated_path(self):
        """High confidence does not shorten an investigation it borrowed."""
        assessment = run(SIBLING)
        self.assertEqual(assessment.final_confidence_level, "HIGH")
        self.assertEqual(assessment.initial_plan_mode, "FULL_INVESTIGATION")
        self.assertEqual(assessment.final_plan_mode, "FULL_INVESTIGATION")

    def test_the_reason_for_the_wide_plan_is_stated(self):
        engine = AdaptiveExecutionOrchestrator(ROOT).confidence_engine
        self.assertIn(
            "EXPERIENCE_TRANSFERRED_NOT_DIRECT", engine.assess(SIBLING).hard_flags
        )

    def test_firsthand_experience_still_earns_the_narrow_plan(self):
        self.assertEqual(run(DIRECT).final_plan_mode, "ACCELERATED_VALIDATION")


class NonDiagnosisTests(unittest.TestCase):
    def test_an_unseen_presentation_completes_instead_of_failing(self):
        """It used to raise. Not knowing is a finding, not a crash."""
        assessment = run(UNSEEN)
        self.assertTrue(assessment.recommendation)
        self.assertTrue(
            {"governed_recommendation", "evidence_fusion_recommendation"}
            & set(assessment.skill_outputs)
        )

    def test_no_hypothesis_is_claimed(self):
        recommendation = run(UNSEEN).recommendation
        self.assertEqual(
            recommendation["leading_hypothesis_id"], "NO_GOVERNED_PATTERN"
        )

    def test_the_recommendation_is_investigative_not_remedial(self):
        recommendation = run(UNSEEN).recommendation
        action = recommendation["recommended_action"].lower()
        self.assertIn("gather", action)
        for remedial in ("restart", "drain", "roll back", "revert"):
            with self.subTest(term=remedial):
                self.assertNotIn(remedial, action)

    def test_it_refuses_to_borrow_an_unrelated_remedy(self):
        self.assertIn(
            "do not apply a remediation drawn from an unrelated pattern",
            run(UNSEEN).recommendation["recommended_action"].lower(),
        )

    def test_the_absence_of_experience_is_named(self):
        recommendation = run(UNSEEN).recommendation
        self.assertIn(
            "NO_COMPARABLE_RECORDED_EXPERIENCE",
            recommendation.get("uncertainty_factors", []),
        )

    def test_it_widens_rather_than_guesses(self):
        assessment = run(UNSEEN)
        self.assertEqual(assessment.final_plan_mode, "FULL_INVESTIGATION")
        self.assertEqual(assessment.initial_confidence_score, 0.0)

    def test_automation_is_not_offered(self):
        readiness = run(UNSEEN).automation_readiness
        self.assertNotEqual(readiness["status"], "CANDIDATE")
        self.assertTrue(readiness["human_approval_enforced"])

    def test_the_case_can_still_become_experience(self):
        """Steps include recording the outcome, so the loop can close."""
        steps = " ".join(run(UNSEEN).recommendation.get("validation_steps", []))
        self.assertIn("governed outcome", steps.lower())


class LayersAgreeTests(unittest.TestCase):
    def test_recall_is_consistent_between_confidence_and_fusion(self):
        """The two layers must not disagree about what a case resembles.

        The confidence engine once matched a pattern that fusion then rejected,
        so a plan was chosen on a premise the next stage refused.
        """
        engine = AdaptiveExecutionOrchestrator(ROOT).confidence_engine
        for scenario in (DIRECT, SIBLING):
            with self.subTest(scenario=scenario):
                engine_pick = engine.assess(scenario).selected_known_error_id
                fusion_pick = run(scenario).recommendation["leading_hypothesis_id"]
                self.assertEqual(engine_pick, fusion_pick)

    def test_neither_layer_invents_a_pattern_for_an_unseen_case(self):
        engine = AdaptiveExecutionOrchestrator(ROOT).confidence_engine
        self.assertIsNone(engine.assess(UNSEEN).selected_known_error_id)
        self.assertEqual(
            run(UNSEEN).recommendation["leading_hypothesis_id"],
            "NO_GOVERNED_PATTERN",
        )


if __name__ == "__main__":
    unittest.main()
