from dataclasses import replace
from pathlib import Path
import unittest

from operational_confidence_engine import OperationalConfidenceEngine
from runtime_confidence_reassessment import RuntimeConfidenceReassessor
from runtime_evidence import RuntimeEvidenceSignal


ROOT = Path(__file__).resolve().parent


def build_reassessor() -> RuntimeConfidenceReassessor:
    return RuntimeConfidenceReassessor(
        ROOT / "config" / "runtime_signal_policy.json",
        ROOT / "config" / "confidence_policy.json",
    )


def build_assessment(scenario_id: str):
    engine = OperationalConfidenceEngine(
        ROOT / "json",
        ROOT / "config" / "confidence_policy.json",
    )
    return engine.assess(scenario_id)


def signal(signal_type: str) -> RuntimeEvidenceSignal:
    return RuntimeEvidenceSignal(
        signal_id=f"TEST-{signal_type}",
        signal_type=signal_type,
        entity_id="COMP-PAY-CONNECTOR",
        discovered_after_skill="due_diligence_validation",
        source_system="TEST",
        description=f"Synthetic {signal_type} signal.",
        data_classification="SYNTHETIC",
        provenance="TEST_FIXTURE",
    )


class ErosionRegressionTests(unittest.TestCase):
    """Penalty behaviour must be unchanged by the bidirectional extension."""

    def test_contradiction_still_erodes_confidence(self):
        initial = build_assessment("SCN-PAY-001")
        updated, result = build_reassessor().reassess(
            initial,
            [signal("CREDIBLE_KNOWLEDGE_CONTRADICTION")],
        )
        self.assertAlmostEqual(updated.confidence_score, 0.770, places=3)
        self.assertEqual(updated.confidence_level, "MEDIUM")
        self.assertEqual(updated.confidence_trend, "ERODING")
        self.assertEqual(updated.drift_status, "ERODING")
        self.assertIn("CREDIBLE_KNOWLEDGE_CONTRADICTION", updated.hard_flags)
        self.assertAlmostEqual(result.applied_penalty, 0.22, places=3)
        self.assertEqual(result.applied_credit, 0.0)


class CreditRequiresExplicitEvidenceTests(unittest.TestCase):
    def test_no_signals_leaves_confidence_unchanged(self):
        eroded = replace(
            build_assessment("SCN-PAY-001"),
            confidence_score=0.70,
            confidence_level="MEDIUM",
            drift_status="STABLE",
            hard_flags=[],
        )
        updated, result = build_reassessor().reassess(eroded, [])
        self.assertAlmostEqual(updated.confidence_score, 0.70, places=3)
        self.assertEqual(result.applied_credit, 0.0)
        self.assertEqual(result.runtime_signal_types, ["DUE_DILIGENCE_PASSED"])

    def test_explicit_credit_signal_raises_confidence_and_trend(self):
        eroded = replace(
            build_assessment("SCN-PAY-001"),
            confidence_score=0.70,
            confidence_level="MEDIUM",
            confidence_trend="ERODING",
            drift_status="STABLE",
            hard_flags=[],
        )
        updated, result = build_reassessor().reassess(
            eroded,
            [signal("VENDOR_INCIDENT_CONFIRMED")],
        )
        self.assertAlmostEqual(updated.confidence_score, 0.78, places=3)
        self.assertEqual(updated.confidence_trend, "IMPROVING")
        self.assertAlmostEqual(result.applied_credit, 0.08, places=3)
        self.assertFalse(result.credit_blocked_by_hard_flags)


class CreditNeverOverpowersPenaltyTests(unittest.TestCase):
    def test_credit_is_capped_per_reassessment(self):
        eroded = replace(
            build_assessment("SCN-PAY-001"),
            confidence_score=0.70,
            confidence_level="MEDIUM",
            drift_status="STABLE",
            hard_flags=[],
        )
        updated, result = build_reassessor().reassess(
            eroded,
            [
                signal("VENDOR_INCIDENT_CONFIRMED"),
                signal("INTERNAL_HYPOTHESIS_ELIMINATED"),
            ],
        )
        # 0.08 + 0.06 = 0.14 requested, capped to the 0.10 policy limit.
        self.assertAlmostEqual(result.applied_credit, 0.10, places=3)
        self.assertAlmostEqual(updated.confidence_score, 0.80, places=3)

    def test_new_hard_flag_blocks_credit_in_the_same_round(self):
        initial = build_assessment("SCN-PAY-001")
        updated, result = build_reassessor().reassess(
            initial,
            [
                signal("CREDIBLE_KNOWLEDGE_CONTRADICTION"),
                signal("VENDOR_INCIDENT_CONFIRMED"),
            ],
        )
        # Penalty applies in full; the credit is withheld because the
        # contradiction raised an unresolved hard flag.
        self.assertAlmostEqual(updated.confidence_score, 0.770, places=3)
        self.assertTrue(result.credit_blocked_by_hard_flags)
        self.assertEqual(result.applied_credit, 0.0)
        self.assertEqual(updated.confidence_trend, "ERODING")

    def test_credit_blocked_while_pre_existing_hard_flag_remains(self):
        initial = build_assessment("SCN-QUEUE-001")
        self.assertIn("RECENT_HIGH_RISK_CHANGE", initial.hard_flags)
        updated, result = build_reassessor().reassess(
            initial,
            [signal("VENDOR_INCIDENT_CONFIRMED")],
        )
        self.assertTrue(result.credit_blocked_by_hard_flags)
        self.assertAlmostEqual(
            updated.confidence_score,
            initial.confidence_score,
            places=3,
        )
        self.assertIn("RECENT_HIGH_RISK_CHANGE", updated.hard_flags)

    def test_runtime_credit_cannot_reach_known_error_confidence(self):
        near_ceiling = replace(
            build_assessment("SCN-PAY-001"),
            confidence_score=0.94,
            drift_status="STABLE",
            hard_flags=[],
        )
        updated, _ = build_reassessor().reassess(
            near_ceiling,
            [signal("VENDOR_INCIDENT_CONFIRMED")],
        )
        # 0.94 + 0.08 would be 1.02; the runtime ceiling holds it at 0.95.
        self.assertAlmostEqual(updated.confidence_score, 0.95, places=3)


class SameRoundOrderingTests(unittest.TestCase):
    """Resolution is applied after flags are raised, within one reassessment.

    A contradiction and its resolution can surface from the same skill. The
    penalty always lands in full; the flag does not stick, so credit is
    allowed. The net effect stays negative, which is the intended asymmetry.
    """

    def test_resolution_beats_a_flag_raised_in_the_same_round(self):
        initial = build_assessment("SCN-PAY-001")
        updated, result = build_reassessor().reassess(
            initial,
            [
                signal("CREDIBLE_KNOWLEDGE_CONTRADICTION"),
                signal("KNOWLEDGE_CONTRADICTION_RESOLVED"),
            ],
        )
        self.assertNotIn(
            "CREDIBLE_KNOWLEDGE_CONTRADICTION",
            updated.hard_flags,
        )
        self.assertFalse(result.credit_blocked_by_hard_flags)
        self.assertAlmostEqual(result.applied_penalty, 0.22, places=3)
        self.assertAlmostEqual(result.applied_credit, 0.05, places=3)
        # 0.99 - 0.22 + 0.05: still a net loss despite same-round resolution.
        self.assertAlmostEqual(updated.confidence_score, 0.82, places=3)
        self.assertLess(updated.confidence_score, initial.confidence_score)


class HardFlagResolverTests(unittest.TestCase):
    def test_flag_clears_only_through_named_resolver(self):
        initial = build_assessment("SCN-QUEUE-001")
        updated, result = build_reassessor().reassess(
            initial,
            [signal("CHANGE_RULED_OUT")],
        )
        self.assertNotIn("RECENT_HIGH_RISK_CHANGE", updated.hard_flags)
        self.assertEqual(
            result.resolved_hard_flags,
            ["RECENT_HIGH_RISK_CHANGE"],
        )

    def test_credit_applies_once_the_flag_is_resolved(self):
        initial = build_assessment("SCN-QUEUE-001")
        updated, result = build_reassessor().reassess(
            initial,
            [signal("CHANGE_RULED_OUT")],
        )
        self.assertFalse(result.credit_blocked_by_hard_flags)
        self.assertAlmostEqual(result.applied_credit, 0.05, places=3)
        self.assertAlmostEqual(
            updated.confidence_score,
            initial.confidence_score + 0.05,
            places=3,
        )

    def test_unrelated_resolver_does_not_clear_other_flags(self):
        initial = replace(
            build_assessment("SCN-QUEUE-001"),
            hard_flags=["RECENT_HIGH_RISK_CHANGE", "OBSERVABILITY_COVERAGE_LOW"],
        )
        updated, result = build_reassessor().reassess(
            initial,
            [signal("CHANGE_RULED_OUT")],
        )
        self.assertNotIn("RECENT_HIGH_RISK_CHANGE", updated.hard_flags)
        self.assertIn("OBSERVABILITY_COVERAGE_LOW", updated.hard_flags)
        # One flag still stands, so the credit stays withheld.
        self.assertTrue(result.credit_blocked_by_hard_flags)


class ContradictionLevelTests(unittest.TestCase):
    def test_resolver_reduces_contradiction_level(self):
        initial = build_assessment("SCN-QUEUE-001")
        updated, _ = build_reassessor().reassess(
            initial,
            [signal("CHANGE_RULED_OUT")],
        )
        self.assertAlmostEqual(
            updated.contradiction_level,
            initial.contradiction_level - 0.2,
            places=3,
        )

    def test_contradiction_level_never_falls_below_zero(self):
        clean = replace(
            build_assessment("SCN-PAY-001"),
            contradiction_level=0.0,
            hard_flags=[],
        )
        updated, _ = build_reassessor().reassess(
            clean,
            [signal("CHANGE_RULED_OUT")],
        )
        self.assertEqual(updated.contradiction_level, 0.0)


if __name__ == "__main__":
    unittest.main()
