"""Vendor evidence moves confidence only through the Step 1 rules.

VENDOR_STATUS_UNKNOWN is derived from the graph rather than declared on a
scenario: a service that depends on an external vendor begins with that
vendor's status unestablished, and the engine learns this by traversal. It
clears only through an explicit resolving signal backed by evidence that
covers every vendor involved.
"""

from dataclasses import replace
from pathlib import Path
import json
import unittest

from operational_confidence_engine import OperationalConfidenceEngine
from runtime_confidence_reassessment import RuntimeConfidenceReassessor
from runtime_evidence import RuntimeEvidenceSignal
from vendor_health_agent import VendorHealthAgent


ROOT = Path(__file__).resolve().parent
JSON_DIR = ROOT / "json"
CONFIG = ROOT / "config"

GITHUB_ONLY = {"AS-GITHUB-ENTERPRISE", "COMP-GITHUB-REPO-ACCESS"}
ALL_PLATFORMS = GITHUB_ONLY | {"AS-TEAMS", "COMP-TEAMS-SIGNALING"}
BOTH_VENDORS = ["GitHub", "Microsoft"]
FRESH = "2026-07-16 09:15:00"


def engine() -> OperationalConfidenceEngine:
    return OperationalConfidenceEngine(JSON_DIR, CONFIG / "confidence_policy.json")


def reassessor() -> RuntimeConfidenceReassessor:
    return RuntimeConfidenceReassessor(
        CONFIG / "runtime_signal_policy.json",
        CONFIG / "confidence_policy.json",
    )


def vendor_signals(entity_ids, required_vendors, as_of: str = FRESH):
    agent = VendorHealthAgent(JSON_DIR, CONFIG / "vendor_health_policy.json")
    assessment = agent.assess(
        scenario_id="SCN-CROSS-GATEWAY-001",
        entity_ids=set(entity_ids),
        as_of=as_of,
    )
    return [
        RuntimeEvidenceSignal(**row, scenario_id="SCN-CROSS-GATEWAY-001")
        for row in agent.signals_for(
            assessment,
            required_vendors=required_vendors,
            entity_id="COMP-SECURE-WEB-GATEWAY",
        )
    ]


def staged_assessment(**overrides):
    """A profile carrying the unknown-vendor flag, ready to be resolved."""
    base = engine().assess("SCN-PAY-001")
    defaults = {
        "hard_flags": ["VENDOR_STATUS_UNKNOWN"],
        "confidence_score": 0.70,
        "confidence_level": "MEDIUM",
        "drift_status": "STABLE",
        "contradiction_level": 0.4,
    }
    defaults.update(overrides)
    return replace(base, **defaults)


class FlagDerivationTests(unittest.TestCase):
    def test_flag_is_derived_from_graph_dependencies(self):
        e = engine()
        self.assertEqual(
            e.external_vendor_dependencies("COMP-GITHUB-REPO-ACCESS"), ["GitHub"]
        )
        self.assertEqual(
            e.external_vendor_dependencies("COMP-TEAMS-SIGNALING"), ["Microsoft"]
        )
        self.assertEqual(
            e.external_vendor_dependencies("COMP-SECURE-WEB-GATEWAY"),
            BOTH_VENDORS,
        )

    def test_internal_only_entities_derive_no_vendor(self):
        e = engine()
        for entity_id in ("COMP-PAY-CONNECTOR", "COMP-ORDER-QUEUE"):
            with self.subTest(entity=entity_id):
                self.assertEqual(e.external_vendor_dependencies(entity_id), [])

    def test_flag_is_not_declared_anywhere_in_the_fixtures(self):
        """Nothing hands the engine this flag; it is inferred."""
        for filename in ("scenarios.json", "health_observations.json", "known_errors.json"):
            payload = (JSON_DIR / filename).read_text(encoding="utf-8")
            with self.subTest(fixture=filename):
                self.assertNotIn("VENDOR_STATUS_UNKNOWN", payload)

    def test_v1_scenarios_keep_their_exact_hard_flags(self):
        e = engine()
        self.assertEqual(e.assess("SCN-PAY-001").hard_flags, [])
        self.assertEqual(e.assess("SCN-PAY-CONTRADICT-001").hard_flags, [])
        self.assertEqual(
            e.assess("SCN-QUEUE-001").hard_flags, ["RECENT_HIGH_RISK_CHANGE"]
        )


class SignalEmissionTests(unittest.TestCase):
    def test_full_vendor_coverage_confirms_status(self):
        types = [s.signal_type for s in vendor_signals(ALL_PLATFORMS, BOTH_VENDORS)]
        self.assertIn("VENDOR_STATUS_CONFIRMED", types)
        self.assertEqual(types.count("EXTERNAL_HYPOTHESIS_ELIMINATED"), 2)

    def test_partial_coverage_does_not_confirm_status(self):
        """One platform's advisory cannot speak for a second vendor."""
        types = [s.signal_type for s in vendor_signals(GITHUB_ONLY, BOTH_VENDORS)]
        self.assertNotIn("VENDOR_STATUS_CONFIRMED", types)
        self.assertEqual(types, ["EXTERNAL_HYPOTHESIS_ELIMINATED"])

    def test_stale_evidence_emits_nothing(self):
        signals = vendor_signals(ALL_PLATFORMS, BOTH_VENDORS, as_of="2026-07-17 12:00:00")
        self.assertEqual(signals, [])

    def test_signals_never_assert_an_internal_cause(self):
        for signal in vendor_signals(ALL_PLATFORMS, BOTH_VENDORS):
            with self.subTest(signal=signal.signal_id):
                self.assertNotIn("GATEWAY_", signal.signal_type)
                self.assertNotIn("CHG-GATEWAY-001", signal.description)


class FlagResolutionTests(unittest.TestCase):
    def test_full_coverage_resolves_the_flag_and_credits_confidence(self):
        staged = staged_assessment()
        updated, result = reassessor().reassess(
            staged, vendor_signals(ALL_PLATFORMS, BOTH_VENDORS)
        )
        self.assertNotIn("VENDOR_STATUS_UNKNOWN", updated.hard_flags)
        self.assertEqual(result.resolved_hard_flags, ["VENDOR_STATUS_UNKNOWN"])
        self.assertGreater(updated.confidence_score, staged.confidence_score)

    def test_partial_coverage_leaves_the_flag_and_withholds_credit(self):
        staged = staged_assessment()
        updated, result = reassessor().reassess(
            staged, vendor_signals(GITHUB_ONLY, BOTH_VENDORS)
        )
        self.assertIn("VENDOR_STATUS_UNKNOWN", updated.hard_flags)
        self.assertTrue(result.credit_blocked_by_hard_flags)
        self.assertEqual(updated.confidence_score, staged.confidence_score)

    def test_credit_stays_capped_under_the_step_one_rules(self):
        """Three crediting signals still cannot exceed the per-round cap."""
        limits = json.loads(
            (CONFIG / "runtime_signal_policy.json").read_text(encoding="utf-8")
        )["limits"]
        cap = float(limits["maximum_credit_per_reassessment"])
        signals = vendor_signals(ALL_PLATFORMS, BOTH_VENDORS)
        self.assertGreaterEqual(len(signals), 3)

        _, result = reassessor().reassess(staged_assessment(), signals)
        self.assertEqual(result.applied_credit, cap)

    def test_eliminating_external_hypotheses_reduces_contradiction(self):
        staged = staged_assessment()
        updated, _ = reassessor().reassess(
            staged, vendor_signals(ALL_PLATFORMS, BOTH_VENDORS)
        )
        self.assertLess(updated.contradiction_level, staged.contradiction_level)

    def test_vendor_signals_do_not_clear_an_internal_hard_flag(self):
        """Healthy vendors say nothing about a risky internal change."""
        staged = staged_assessment(
            hard_flags=["VENDOR_STATUS_UNKNOWN", "RECENT_HIGH_RISK_CHANGE"]
        )
        updated, result = reassessor().reassess(
            staged, vendor_signals(ALL_PLATFORMS, BOTH_VENDORS)
        )
        self.assertNotIn("VENDOR_STATUS_UNKNOWN", updated.hard_flags)
        self.assertIn("RECENT_HIGH_RISK_CHANGE", updated.hard_flags)
        # An internal flag still stands, so credit remains withheld.
        self.assertTrue(result.credit_blocked_by_hard_flags)


class AcceleratedPathGateTests(unittest.TestCase):
    def test_unknown_vendor_status_blocks_the_accelerated_path(self):
        modes = {
            m["mode_id"]: m
            for m in json.loads(
                (CONFIG / "orchestration_policies.json").read_text(encoding="utf-8")
            )["modes"]
        }
        self.assertIn(
            "VENDOR_STATUS_UNKNOWN",
            modes["ACCELERATED_VALIDATION"]["entry_conditions"]["disallowed_hard_flags"],
        )


if __name__ == "__main__":
    unittest.main()
