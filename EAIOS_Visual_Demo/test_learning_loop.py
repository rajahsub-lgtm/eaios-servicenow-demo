"""The loop that turns a first encounter into a second one.

A proposal read from a manual, validated by a human, applied, and recorded is
only learning if the next occurrence meets it as experience. Everything here
asserts that circuit: that the pattern is recalled through the ordinary path,
that what happened last time changes what happens this time, and that a
rejection is weighed without being made permanent.
"""

from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from case_fingerprint import CaseFingerprinter
from documented_reasoning import DocumentationReasoner
from evidence_fusion_agent import EvidenceFusionAgent
from operational_confidence_engine import OperationalConfidenceEngine
from outcome_feedback import (
    OutcomeFeedbackStore,
    OutcomeInput,
    feedback_from_assessment,
)
from pattern_learning import PatternLearner, Refutation, ValidationDecision


ROOT = Path(__file__).resolve().parent
FIRST = "SCN-NOVEL-INDEX-001"
RECURRENCE = "SCN-INDEX-RECUR-001"


class Loop:
    """One scratch copy of the fixtures, driven through the arc."""

    def __init__(self, directory: str) -> None:
        self.json_dir = Path(directory) / "json"
        shutil.copytree(ROOT / "json", self.json_dir)
        self.learner = PatternLearner(self.json_dir)

    def run(self, scenario_id: str = FIRST):
        return AdaptiveExecutionOrchestrator(
            ROOT, json_dir=self.json_dir
        ).execute(correlation_id=f"T-{scenario_id}", scenario_id=scenario_id)

    def engine(self) -> OperationalConfidenceEngine:
        return OperationalConfidenceEngine(
            self.json_dir, ROOT / "config" / "confidence_policy.json"
        )

    def validate(self, assessment, decision: ValidationDecision):
        recommendation = assessment.recommendation
        return self.learner.learn(
            assessment=assessment,
            decision=decision,
            fingerprint=CaseFingerprinter(self.json_dir).for_scenario(FIRST),
            document_id=recommendation["leading_hypothesis_id"],
            proposed_cause=recommendation["leading_hypothesis_title"],
            proposed_action=recommendation["recommended_action"],
            trigger_metric_id="MET-INDEX-LAG",
            external_service_id="SVC-SEARCH-001",
        )

    def record(self, assessment, pattern_id: str, *, worked: bool, count: int = 1):
        store = OutcomeFeedbackStore(
            self.json_dir / "runtime_outcome_feedback.json"
        )
        for index in range(count):
            store.append(
                feedback_from_assessment(
                    assessment,
                    OutcomeInput(
                        approval_decision="Approved",
                        human_modification="None",
                        action_performed="Validated remedy applied",
                        outcome="Successful" if worked else "Unsuccessful",
                        recovery_minutes=22.0 if worked else 95.0,
                        recurrence_within_24h=not worked,
                        evidence_usefulness_score=88.0 if worked else 30.0,
                        recorded_at=(
                            datetime(2026, 7, 25) + timedelta(days=index)
                        ).strftime("%Y-%m-%d 09:00:00"),
                    ),
                    outcome_id=f"OUT-T-{index:03d}",
                    known_error_id=pattern_id,
                )
            )


CONFIRMED = ValidationDecision(
    decision="CONFIRMED",
    validated_by="k.osei@example.com",
    decided_at="2026-07-24 16:30:00",
)


class ValidationCreatesAPatternTests(unittest.TestCase):
    def test_a_validated_proposal_becomes_a_recallable_pattern(self):
        """Recorded but unrecallable is not learning."""
        with TemporaryDirectory() as directory:
            loop = Loop(directory)
            pattern = loop.validate(loop.run(), CONFIRMED)
            self.assertEqual(
                loop.engine().assess(RECURRENCE).selected_known_error_id,
                pattern.known_error_id,
            )

    def test_the_pattern_is_provisional_not_established(self):
        with TemporaryDirectory() as directory:
            loop = Loop(directory)
            pattern = loop.validate(loop.run(), CONFIRMED)
            self.assertEqual(pattern.knowledge_status, "Provisional")
            self.assertEqual(pattern.historical_occurrences, 1)
            self.assertTrue(pattern.requires_human_approval)

    def test_it_records_where_it_came_from_and_who_confirmed_it(self):
        with TemporaryDirectory() as directory:
            loop = Loop(directory)
            pattern = loop.validate(loop.run(), CONFIRMED)
            self.assertEqual(pattern.learned_from_document_id, "RB-SEARCH-001")
            self.assertEqual(pattern.validated_by, "k.osei@example.com")
            self.assertEqual(pattern.hypothesis_class, "LEARNED")

    def test_a_correction_replaces_the_proposed_cause(self):
        """The correction is the most informative thing that happened."""
        with TemporaryDirectory() as directory:
            loop = Loop(directory)
            pattern = loop.validate(
                loop.run(),
                ValidationDecision(
                    decision="CORRECTED",
                    validated_by="k.osei@example.com",
                    decided_at="2026-07-24 16:30:00",
                    corrected_cause="A stalled segment merge held the lock.",
                    corrected_action="Clear the merge before any restart.",
                ),
            )
            self.assertEqual(
                pattern.probable_cause, "A stalled segment merge held the lock."
            )
            self.assertEqual(pattern.validation_decision, "CORRECTED")

    def test_an_unknown_decision_is_refused(self):
        with self.assertRaises(ValueError):
            ValidationDecision(
                decision="MAYBE", validated_by="x", decided_at="2026-07-24 00:00:00"
            )


class TheSecondEncounterDiffersTests(unittest.TestCase):
    def _arc(self, directory: str, *, worked: bool):
        loop = Loop(directory)
        first = loop.run()
        pattern = loop.validate(first, CONFIRMED)
        loop.record(first, pattern.known_error_id, worked=worked)
        return loop, first, loop.run(RECURRENCE)

    def test_experience_replaces_the_manual(self):
        with TemporaryDirectory() as directory:
            _, first, second = self._arc(directory, worked=True)
            self.assertEqual(
                first.recommendation["leading_hypothesis_id"], "RB-SEARCH-001"
            )
            self.assertIn(
                "KE-LEARNED",
                second.recommendation["leading_hypothesis_id"],
            )

    def test_a_remedy_that_worked_outranks_one_that_did_not(self):
        """The whole point: what happened last time changes this time."""
        with TemporaryDirectory() as directory:
            _, _, good = self._arc(directory, worked=True)
        with TemporaryDirectory() as directory:
            _, _, bad = self._arc(directory, worked=False)
        self.assertGreater(
            good.initial_confidence_score, bad.initial_confidence_score
        )

    def test_a_failed_remedy_is_named_not_merely_averaged(self):
        with TemporaryDirectory() as directory:
            loop, _, bad = self._arc(directory, worked=False)
            self.assertIn(
                "REMEDY_PREVIOUSLY_INEFFECTIVE",
                loop.engine().assess(RECURRENCE).hard_flags,
            )

    def test_a_successful_remedy_raises_no_ineffectiveness_flag(self):
        with TemporaryDirectory() as directory:
            loop, _, _ = self._arc(directory, worked=True)
            self.assertNotIn(
                "REMEDY_PREVIOUSLY_INEFFECTIVE",
                loop.engine().assess(RECURRENCE).hard_flags,
            )

    def test_one_case_never_earns_the_narrow_plan(self):
        with TemporaryDirectory() as directory:
            _, _, second = self._arc(directory, worked=True)
            self.assertEqual(second.final_plan_mode, "FULL_INVESTIGATION")
            self.assertTrue(second.recommendation["human_approval_required"])


class MaturityTests(unittest.TestCase):
    def _confidence_after(self, cases: int) -> float:
        with TemporaryDirectory() as directory:
            loop = Loop(directory)
            first = loop.run()
            pattern = loop.validate(first, CONFIRMED)
            loop.record(first, pattern.known_error_id, worked=True, count=cases)
            return loop.engine().assess(RECURRENCE).confidence_score

    def test_confidence_climbs_as_cases_accumulate(self):
        scores = [self._confidence_after(n) for n in (1, 3, 5, 8)]
        self.assertEqual(scores, sorted(scores))
        self.assertLess(scores[0], scores[-1])

    def test_an_established_pattern_sheds_the_provisional_penalty(self):
        """Without promotion the discount is permanent and the system can
        never finish learning anything.

        Fifteen cases, not twelve: promotion no longer carries its own
        sufficiency threshold and reads minimum_outcome_sample instead, so a
        pattern can no longer shed its provisional penalty while still being
        flagged as insufficiently evidenced.
        """
        with TemporaryDirectory() as directory:
            loop = Loop(directory)
            first = loop.run()
            pattern = loop.validate(first, CONFIRMED)
            loop.record(first, pattern.known_error_id, worked=True, count=15)
            assessment = loop.engine().assess(RECURRENCE)
            self.assertNotIn(
                "PATTERN_PROVISIONAL_NOT_ESTABLISHED", assessment.hard_flags
            )

    def test_promotion_reverses_on_its_own_when_the_rate_falls(self):
        """Evaluated from the record, so nothing has to remember to demote."""
        with TemporaryDirectory() as directory:
            loop = Loop(directory)
            first = loop.run()
            pattern = loop.validate(first, CONFIRMED)
            loop.record(first, pattern.known_error_id, worked=False, count=15)
            self.assertIn(
                "PATTERN_PROVISIONAL_NOT_ESTABLISHED",
                loop.engine().assess(RECURRENCE).hard_flags,
            )


class RejectionIsEvidenceNotABanTests(unittest.TestCase):
    def _rejected(self, directory: str):
        loop = Loop(directory)
        first = loop.run()
        refutation = loop.validate(
            first,
            ValidationDecision(
                decision="REJECTED",
                validated_by="m.varga@example.com",
                decided_at="2026-07-24 17:05:00",
                reason="Lag tracked a storage failover, not the indexer.",
            ),
        )
        return loop, refutation

    def test_a_rejection_mints_no_pattern(self):
        with TemporaryDirectory() as directory:
            loop, refutation = self._rejected(directory)
            self.assertIsInstance(refutation, Refutation)
            self.assertEqual(loop.learner.patterns.list(), [])

    def test_the_rejection_is_recorded_with_who_and_why(self):
        with TemporaryDirectory() as directory:
            _, refutation = self._rejected(directory)
            self.assertEqual(refutation.rejected_by, "m.varga@example.com")
            self.assertIn("storage failover", refutation.reason)

    def test_the_account_is_lowered_not_removed(self):
        """A human can reject wrongly. A system that treats one rejection as
        final has made that person's error unfalsifiable."""
        with TemporaryDirectory() as directory:
            loop, _ = self._rejected(directory)
            case = CaseFingerprinter(loop.json_dir).for_scenario(FIRST)
            ranked = DocumentationReasoner(loop.json_dir).propose(
                case, assessed_at=datetime(2026, 8, 14)
            )
            offered = {item.document_id for item in ranked}
            self.assertIn("RB-SEARCH-001", offered)

    def test_the_rejected_account_scores_below_its_unrejected_self(self):
        baseline = DocumentationReasoner(ROOT / "json").propose(
            CaseFingerprinter(ROOT / "json").for_scenario(FIRST),
            assessed_at=datetime(2026, 8, 14),
        )[0]
        with TemporaryDirectory() as directory:
            loop, _ = self._rejected(directory)
            after = next(
                item
                for item in DocumentationReasoner(loop.json_dir).propose(
                    CaseFingerprinter(loop.json_dir).for_scenario(FIRST),
                    assessed_at=datetime(2026, 8, 14),
                )
                if item.document_id == "RB-SEARCH-001"
            )
            self.assertLess(after.support, baseline.support)
            self.assertGreater(after.support, 0.0)
            self.assertEqual(after.prior_rejections, 1)

    def test_the_next_reviewer_is_told_it_was_rejected_before(self):
        with TemporaryDirectory() as directory:
            loop, _ = self._rejected(directory)
            action = EvidenceFusionAgent(loop.json_dir).analyze(
                FIRST
            ).recommended_action
            self.assertIn("rejected", action.lower())
            self.assertIn("m.varga@example.com", action)


class LayersAgreeTests(unittest.TestCase):
    def test_both_layers_recall_the_learned_pattern(self):
        with TemporaryDirectory() as directory:
            loop = Loop(directory)
            pattern = loop.validate(loop.run(), CONFIRMED)
            fusion = EvidenceFusionAgent(loop.json_dir).analyze(RECURRENCE)
            self.assertEqual(
                loop.engine().assess(RECURRENCE).selected_known_error_id,
                fusion.leading_hypothesis.hypothesis_id,
            )
            self.assertEqual(
                fusion.leading_hypothesis.hypothesis_id, pattern.known_error_id
            )


if __name__ == "__main__":
    unittest.main()


class WeakRecallReopensTheSearchTests(unittest.TestCase):
    """A recalled pattern used to end the search.

    That is right when the pattern is strong and wrong when it is not. Thin
    experience is exactly the case where the written record is most likely to
    know something the system does not — including material published since,
    which a run that consults documentation only when it remembers nothing
    would never find.
    """

    def _second(self, directory: str):
        loop = Loop(directory)
        first = loop.run()
        pattern = loop.validate(first, CONFIRMED)
        loop.record(first, pattern.known_error_id, worked=True)
        return loop, loop.run(RECURRENCE)

    def test_a_weak_pattern_does_not_end_the_search(self):
        with TemporaryDirectory() as directory:
            loop, _ = self._second(directory)
            assessment = loop.engine().assess(RECURRENCE)
            self.assertLess(
                assessment.confidence_score,
                loop.engine().documentation.reconsult_below,
            )
            self.assertIn(
                "WEAK_PATTERN_DOCUMENTATION_RECONSULTED", assessment.hard_flags
            )

    def test_the_documentation_is_carried_as_alternatives_to_investigate(self):
        with TemporaryDirectory() as directory:
            _, second = self._second(directory)
            alternatives = set(
                second.recommendation["alternative_hypothesis_ids"]
            )
            self.assertIn("RB-SEARCH-001", alternatives)
            self.assertIn("PIR-SEARCH-021", alternatives)

    def test_knowledge_published_since_is_found_and_named(self):
        """The review written after the first occurrence is the material most
        likely to change the second response."""
        with TemporaryDirectory() as directory:
            loop, second = self._second(directory)
            self.assertIn(
                "NEWER_DOCUMENTATION_AVAILABLE",
                loop.engine().assess(RECURRENCE).hard_flags,
            )
            action = second.recommendation["recommended_action"]
            self.assertIn("PIR-SEARCH-021", action)
            self.assertIn("published since", action)

    def test_the_disclosure_survives_the_recommendation_agent(self):
        """Twice now a generic restatement has dropped exactly this kind of
        qualification on the way through."""
        with TemporaryDirectory() as directory:
            _, second = self._second(directory)
            self.assertIn(
                "Read it before acting on recorded experience alone",
                second.recommendation["recommended_action"],
            )

    def test_the_disclosure_is_not_duplicated(self):
        with TemporaryDirectory() as directory:
            _, second = self._second(directory)
            action = second.recommendation["recommended_action"]
            self.assertEqual(action.count("PIR-SEARCH-021"), 1)

    def test_documentation_never_displaces_experience_as_the_lead(self):
        """A documented score and an experience score are not the same
        measurement, so the higher number must not win on comparison."""
        with TemporaryDirectory() as directory:
            loop, second = self._second(directory)
            assessment = loop.engine().assess(RECURRENCE)
            leading = assessment.candidate_assessments[0]
            self.assertEqual(leading.experience_class, "DIRECT")
            documented = [
                c
                for c in assessment.candidate_assessments
                if c.experience_class == "DOCUMENTED"
            ]
            self.assertTrue(documented)
            self.assertGreater(
                max(c.confidence_score for c in documented),
                leading.confidence_score,
            )
            self.assertEqual(
                assessment.selected_known_error_id, leading.known_error_id
            )

    def test_the_plan_stays_wide_and_runs_the_knowledge_search(self):
        with TemporaryDirectory() as directory:
            _, second = self._second(directory)
            self.assertEqual(second.final_plan_mode, "FULL_INVESTIGATION")
            self.assertIn(
                "governed_knowledge_retrieval", second.completed_skills
            )

    def test_a_strong_pattern_does_not_reopen_the_search(self):
        """Reconsultation is for thin evidence, not a blanket second pass."""
        engine = OperationalConfidenceEngine(
            ROOT / "json", ROOT / "config" / "confidence_policy.json"
        )
        assessment = engine.assess("SCN-PAY-001")
        self.assertGreater(
            assessment.confidence_score, engine.documentation.reconsult_below
        )
        self.assertNotIn(
            "WEAK_PATTERN_DOCUMENTATION_RECONSULTED", assessment.hard_flags
        )


class FusionSeesWhatTheEngineSeesTests(unittest.TestCase):
    def test_runtime_outcomes_count_as_history_in_both_layers(self):
        """Fusion read only the shipped history, so the two layers were
        reasoning from different pasts: a pattern could accumulate cases that
        only one of them could see."""
        with TemporaryDirectory() as directory:
            loop = Loop(directory)
            first = loop.run()
            pattern = loop.validate(first, CONFIRMED)
            loop.record(first, pattern.known_error_id, worked=True, count=4)
            fusion = EvidenceFusionAgent(loop.json_dir).analyze(RECURRENCE)
            self.assertEqual(
                fusion.leading_hypothesis.outcome_history.occurrences, 4
            )
