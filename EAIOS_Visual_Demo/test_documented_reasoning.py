"""Reading the manual when nothing has been tried.

The governed non-diagnosis was honest and terminal. It declined to guess, which
was right, and then left the case with nowhere to go — so a first encounter
could never become a second one, and the system could never learn anything it
had not already been told.

Documentation reopens that path without pretending to be experience. Everything
asserted here is about keeping those two things apart: what a procedure is
allowed to buy, what it must disclose, and what it can never reach.
"""

from datetime import datetime
from pathlib import Path
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from case_fingerprint import CaseFingerprinter
from documented_reasoning import DocumentationReasoner
from evidence_fusion_agent import EvidenceFusionAgent
from operational_confidence_engine import OperationalConfidenceEngine


ROOT = Path(__file__).resolve().parent
JSON = ROOT / "json"

DOCUMENTED = "SCN-NOVEL-INDEX-001"
UNDOCUMENTED = "SCN-UNDOCUMENTED-001"
EXPERIENCED = "SCN-PAY-001"

_runs: dict = {}


def run(scenario_id: str):
    if scenario_id not in _runs:
        _runs[scenario_id] = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id=f"DOC-{scenario_id}", scenario_id=scenario_id
        )
    return _runs[scenario_id]


def engine() -> OperationalConfidenceEngine:
    return OperationalConfidenceEngine(
        JSON, ROOT / "config" / "confidence_policy.json"
    )


def proposals(scenario_id: str):
    reasoner = DocumentationReasoner(JSON)
    return reasoner, reasoner.propose(
        CaseFingerprinter(JSON).for_scenario(scenario_id),
        assessed_at=datetime(2026, 7, 24),
    )


class DocumentSelectionTests(unittest.TestCase):
    def test_a_current_trusted_runbook_outranks_a_lapsed_wiki_page(self):
        _, ranked = proposals(DOCUMENTED)
        self.assertEqual(ranked[0].document_id, "RB-SEARCH-001")
        self.assertEqual(ranked[1].document_id, "WIKI-SEARCH-014")

    def test_the_ceiling_scales_rather_than_clips(self):
        """Clipping would hand both documents the same confidence the moment
        each cleared the ceiling, discarding the ranking just established."""
        reasoner, ranked = proposals(DOCUMENTED)
        scores = [reasoner.confidence_for(item) for item in ranked]
        self.assertGreater(scores[0], scores[1])
        for score in scores:
            self.assertLessEqual(score, reasoner.maximum_confidence)

    def test_a_document_about_another_component_is_not_offered(self):
        _, ranked = proposals(DOCUMENTED)
        for item in ranked:
            with self.subTest(document=item.document_id):
                self.assertIn("SEARCH", item.document_id)

    def test_nothing_is_proposed_where_nothing_is_written(self):
        _, ranked = proposals(UNDOCUMENTED)
        self.assertEqual(ranked, [])


class DisclosureTests(unittest.TestCase):
    def test_the_source_document_is_named_in_the_recommendation(self):
        action = run(DOCUMENTED).recommendation["recommended_action"]
        self.assertIn("RB-SEARCH-001", action)
        self.assertIn("Knowledge Platform Team", action)

    def test_the_absence_of_experience_is_stated_not_implied(self):
        action = run(DOCUMENTED).recommendation["recommended_action"].lower()
        self.assertIn("nothing comparable has been resolved", action)
        self.assertIn("proposal for human validation, not a diagnosis", action)

    def test_the_proposal_is_not_restated_as_a_leading_hypothesis(self):
        """The generic wording once overwrote this and called a runbook a
        leading hypothesis, dropping both the source and the disclosure."""
        action = run(DOCUMENTED).recommendation["recommended_action"]
        self.assertNotIn("leading hypothesis rather than confirmed", action)

    def test_the_uncertainty_names_documentation_as_the_only_basis(self):
        factors = run(DOCUMENTED).recommendation["uncertainty_factors"]
        self.assertIn("CAUSE_PROPOSED_FROM_DOCUMENTATION_ONLY", factors)
        self.assertIn("NO_COMPARABLE_RECORDED_EXPERIENCE", factors)

    def test_the_document_appears_in_the_evidence_ledger_with_its_age(self):
        ledger = run(DOCUMENTED).recommendation["evidence_ledger"]
        entry = next(
            row for row in ledger if row["evidence_id"] == "RB-SEARCH-001"
        )
        self.assertEqual(entry["evidence_class"], "DOCUMENTED_PROCEDURE")
        self.assertIn("last validated", entry["rationale"])


class CeilingTests(unittest.TestCase):
    def test_documentation_never_narrows_the_plan(self):
        self.assertEqual(run(DOCUMENTED).final_plan_mode, "FULL_INVESTIGATION")

    def test_documentation_stays_below_the_experienced_case(self):
        self.assertLess(
            run(DOCUMENTED).initial_confidence_score,
            run(EXPERIENCED).initial_confidence_score,
        )

    def test_it_cannot_reach_the_medium_band(self):
        """The ceiling sits below MEDIUM deliberately, so a documented
        proposal cannot be mistaken for a validated one at a glance."""
        e = engine()
        assessment = e.assess(DOCUMENTED)
        self.assertEqual(assessment.confidence_level, "LOW")
        self.assertLess(
            e.documentation.maximum_confidence,
            float(e.policy["levels"]["MEDIUM"]),
        )

    def test_automation_readiness_is_suspended_categorically(self):
        readiness = run(DOCUMENTED).automation_readiness
        self.assertNotEqual(readiness["status"], "CANDIDATE")
        self.assertTrue(readiness["human_approval_enforced"])

    def test_approval_is_still_mandatory(self):
        self.assertTrue(run(DOCUMENTED).recommendation["human_approval_required"])


class NonDiagnosisSurvivesTests(unittest.TestCase):
    """Documentation must not quietly replace the ability to say nothing."""

    def test_a_case_with_no_procedure_still_refuses_to_guess(self):
        recommendation = run(UNDOCUMENTED).recommendation
        self.assertEqual(
            recommendation["leading_hypothesis_id"], "NO_GOVERNED_PATTERN"
        )
        self.assertEqual(run(UNDOCUMENTED).initial_confidence_score, 0.0)

    def test_it_still_refuses_to_borrow_a_remedy(self):
        action = run(UNDOCUMENTED).recommendation["recommended_action"].lower()
        self.assertIn(
            "do not apply a remediation drawn from an unrelated pattern", action
        )


class LayersAgreeTests(unittest.TestCase):
    def test_confidence_and_fusion_choose_the_same_document(self):
        """The two layers disagreed twice before; each time a plan was chosen
        on a premise the next stage refused."""
        fusion = EvidenceFusionAgent(JSON).analyze(DOCUMENTED)
        self.assertEqual(
            engine().assess(DOCUMENTED).selected_known_error_id,
            fusion.leading_hypothesis.hypothesis_id,
        )
        self.assertEqual(
            fusion.leading_hypothesis.hypothesis_type,
            "DOCUMENTED_NOT_EXPERIENCED",
        )

    def test_neither_layer_reads_a_manual_that_does_not_exist(self):
        self.assertIsNone(engine().assess(UNDOCUMENTED).selected_known_error_id)
        self.assertEqual(
            EvidenceFusionAgent(JSON)
            .analyze(UNDOCUMENTED)
            .leading_hypothesis.hypothesis_type,
            "NO_DIAGNOSIS",
        )


class EligibilityTests(unittest.TestCase):
    def test_a_deprecated_procedure_is_withdrawn_not_merely_weak(self):
        reasoner = DocumentationReasoner(JSON)
        self.assertEqual(reasoner.policy["trust_weights"]["Deprecated"], 0.0)

    def test_freshness_decays_rather_than_expiring_on_a_date(self):
        reasoner = DocumentationReasoner(JSON)
        full = float(reasoner.policy["freshness"]["full_credit_days"])
        none = float(reasoner.policy["freshness"]["no_credit_days"])
        self.assertGreater(none, full)
        _, ranked = proposals(DOCUMENTED)
        ageing = next(
            item for item in ranked if item.document_id == "WIKI-SEARCH-014"
        )
        self.assertGreater(ageing.freshness_credit, 0.0)
        self.assertLess(ageing.freshness_credit, 1.0)


if __name__ == "__main__":
    unittest.main()
