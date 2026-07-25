from pathlib import Path
import unittest

from evidence_fusion_agent import EvidenceFusionAgent


ROOT = Path(__file__).resolve().parent


class EvidenceFusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = EvidenceFusionAgent(ROOT / "json")

    def test_payment_selects_accelerated_known_error_validation(self):
        result = self.agent.analyze("SCN-PAY-001")
        self.assertEqual(
            result.selected_strategy,
            "Known Error Accelerated Validation",
        )
        self.assertEqual(result.confidence_level, "HIGH")
        self.assertGreaterEqual(result.confidence_score, 0.85)
        self.assertEqual(result.leading_hypothesis.hypothesis_id, "KE-PAY-001")

    def test_payment_uses_collective_outcome_history(self):
        result = self.agent.analyze("SCN-PAY-001")
        history = result.leading_hypothesis.outcome_history
        self.assertEqual(history.occurrences, 50)
        self.assertEqual(history.successful_outcomes, 49)
        self.assertEqual(history.success_rate, 0.98)
        self.assertEqual(history.dominant_prior_confidence, "HIGH")

    def test_queue_selects_full_investigation_with_medium_confidence(self):
        result = self.agent.analyze("SCN-QUEUE-001")
        self.assertEqual(result.selected_strategy, "Full Investigation")
        self.assertEqual(result.confidence_level, "MEDIUM")
        self.assertEqual(result.leading_hypothesis.hypothesis_id, "KE-QUEUE-002")
        self.assertIn("RECENT_HIGH_RISK_CHANGE", result.uncertainty_factors)
        self.assertIn("CROSS_SERVICE_DEGRADATION", result.uncertainty_factors)
        self.assertIn(
            "INFERRED_CHANGE_OR_CAUSAL_HYPOTHESIS",
            result.uncertainty_factors,
        )

    def test_queue_retains_change_as_alternative_not_fact(self):
        result = self.agent.analyze("SCN-QUEUE-001")
        alternatives = {
            item.hypothesis_id: item for item in result.alternative_hypotheses
        }
        self.assertIn("CHG-QUEUE-006", alternatives)
        self.assertEqual(
            alternatives["CHG-QUEUE-006"].hypothesis_type,
            "CHANGE_CORRELATION",
        )
        self.assertIn(
            "TEMPORAL_CORRELATION_IS_NOT_CAUSATION",
            alternatives["CHG-QUEUE-006"].uncertainty_factors,
        )

    def test_rejected_knowledge_is_not_fused(self):
        result = self.agent.analyze("SCN-QUEUE-001")
        ledger_ids = {item.evidence_id for item in result.evidence_ledger}
        self.assertNotIn("WIKI-QUEUE-011", ledger_ids)
        self.assertIn("WIKI-QUEUE-011", result.rejected_evidence_ids)

    def test_evidence_classes_remain_separate(self):
        result = self.agent.analyze("SCN-PAY-001")
        classes = {item.evidence_class for item in result.evidence_ledger}
        self.assertIn("OBSERVED_TELEMETRY", classes)
        self.assertIn("AUTHORITATIVE_RELATIONSHIP", classes)
        self.assertIn("COLLECTIVE_LEARNING", classes)
        self.assertIn("FREE_TEXT_KNOWLEDGE", classes)
        self.assertIn("STRUCTURED_ENTERPRISE_RECORD", classes)

    def test_human_approval_is_mandatory_for_both_scenarios(self):
        for scenario_id in ("SCN-PAY-001", "SCN-QUEUE-001"):
            result = self.agent.analyze(scenario_id)
            self.assertTrue(result.human_approval_required)
            self.assertEqual(
                result.safety_status,
                "REQUIRES_HUMAN_APPROVAL",
            )
            self.assertIn(
                "SERVICENOW_APPROVAL_REQUIRED_BEFORE_ACTION",
                result.guardrail_reasons,
            )

    def test_expected_strategy_field_is_not_used_by_runtime(self):
        agent = EvidenceFusionAgent(ROOT / "json")
        agent.scenario_by_id["SCN-PAY-001"]["expected_strategy"] = (
            "Full Investigation"
        )
        result = agent.analyze("SCN-PAY-001")
        self.assertEqual(
            result.selected_strategy,
            "Known Error Accelerated Validation",
        )


if __name__ == "__main__":
    unittest.main()
