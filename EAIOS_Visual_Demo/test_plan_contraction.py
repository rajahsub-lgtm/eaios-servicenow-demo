"""Planning must contract as well as expand.

The planner selects a mode purely from the confidence profile, so an improved
profile should reduce scope exactly as a degraded profile widens it. These
tests pin that behaviour and the policy margins it depends on.
"""

from dataclasses import replace
from pathlib import Path
import json
import unittest

from adaptive_planner import AdaptivePlanner
from operational_confidence_engine import OperationalConfidenceEngine
from runtime_confidence_reassessment import RuntimeConfidenceReassessor
from runtime_evidence import RuntimeEvidenceSignal
from skill_resolver import SkillResolver


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"

ACCELERATED = "ACCELERATED_VALIDATION"
FULL = "FULL_INVESTIGATION"


def build_planner() -> AdaptivePlanner:
    engine = OperationalConfidenceEngine(
        ROOT / "json",
        CONFIG / "confidence_policy.json",
    )
    resolver = SkillResolver(
        CONFIG / "skill_catalog.json",
        CONFIG / "agent_registry.json",
    )
    return AdaptivePlanner(
        engine,
        resolver,
        CONFIG / "orchestration_policies.json",
    )


def build_reassessor() -> RuntimeConfidenceReassessor:
    return RuntimeConfidenceReassessor(
        CONFIG / "runtime_signal_policy.json",
        CONFIG / "confidence_policy.json",
    )


def baseline_confidence():
    return OperationalConfidenceEngine(
        ROOT / "json",
        CONFIG / "confidence_policy.json",
    ).assess("SCN-PAY-001")


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


CONTRADICTION = [signal("CREDIBLE_KNOWLEDGE_CONTRADICTION")]
RESOLUTION = [
    signal("KNOWLEDGE_CONTRADICTION_RESOLVED"),
    signal("INTERNAL_HYPOTHESIS_ELIMINATED"),
]


class ExpansionContractionCycleTests(unittest.TestCase):
    def test_full_expansion_and_contraction_cycle(self):
        planner = build_planner()
        reassessor = build_reassessor()

        base = baseline_confidence()
        self.assertEqual(
            planner.plan_from_confidence(base).orchestration_mode,
            ACCELERATED,
        )

        eroded, _ = reassessor.reassess(base, CONTRADICTION)
        self.assertEqual(
            planner.plan_from_confidence(eroded).orchestration_mode,
            FULL,
        )

        recovered, _ = reassessor.reassess(eroded, RESOLUTION)
        self.assertEqual(
            planner.plan_from_confidence(recovered).orchestration_mode,
            ACCELERATED,
        )

        re_eroded, _ = reassessor.reassess(recovered, CONTRADICTION)
        self.assertEqual(
            planner.plan_from_confidence(re_eroded).orchestration_mode,
            FULL,
        )

    def test_contraction_reduces_skills_and_agents(self):
        planner = build_planner()
        reassessor = build_reassessor()

        eroded, _ = reassessor.reassess(baseline_confidence(), CONTRADICTION)
        wide = planner.plan_from_confidence(eroded)

        recovered, _ = reassessor.reassess(eroded, RESOLUTION)
        narrow = planner.plan_from_confidence(recovered)

        self.assertLess(
            len(narrow.required_skills),
            len(wide.required_skills),
        )
        self.assertLess(
            narrow.reasoning_agent_count,
            wide.reasoning_agent_count,
        )

    def test_contraction_substitutes_skills_rather_than_subsetting(self):
        """The two modes are different skill sets, not nested ones.

        Narrowing the plan is a pivot, not a truncation: it drops the four
        deep-investigation skills and introduces two accelerated-path skills
        that were never part of the wide plan. Only semantic context is
        common to both, so contraction still schedules work rather than
        simply cancelling it.
        """
        planner = build_planner()
        reassessor = build_reassessor()

        eroded, _ = reassessor.reassess(baseline_confidence(), CONTRADICTION)
        wide = set(planner.plan_from_confidence(eroded).required_skills)

        recovered, _ = reassessor.reassess(eroded, RESOLUTION)
        narrow = set(planner.plan_from_confidence(recovered).required_skills)

        self.assertEqual(wide & narrow, {"semantic_context"})
        self.assertEqual(
            narrow - wide,
            {"due_diligence_validation", "governed_recommendation"},
        )
        self.assertFalse(
            narrow.issubset(wide),
            "Contraction is a substitution; if this ever becomes a subset "
            "the execution model in Step 3 can be simplified.",
        )

    def test_planner_shows_no_hysteresis(self):
        """A profile's history must not affect the plan it produces."""
        planner = build_planner()
        reassessor = build_reassessor()

        eroded, _ = reassessor.reassess(baseline_confidence(), CONTRADICTION)
        recovered, _ = reassessor.reassess(eroded, RESOLUTION)

        equivalent = replace(
            baseline_confidence(),
            confidence_score=recovered.confidence_score,
            confidence_level=recovered.confidence_level,
            drift_status=recovered.drift_status,
            contradiction_level=recovered.contradiction_level,
            hard_flags=list(recovered.hard_flags),
        )

        from_history = planner.plan_from_confidence(recovered)
        from_scratch = planner.plan_from_confidence(equivalent)
        self.assertEqual(
            from_history.orchestration_mode,
            from_scratch.orchestration_mode,
        )
        self.assertEqual(
            from_history.required_skills,
            from_scratch.required_skills,
        )


class ContractionMarginTests(unittest.TestCase):
    def test_credit_cap_can_clear_the_high_threshold_after_erosion(self):
        """Guard the narrow margin that makes contraction possible at all.

        Erosion drops confidence below HIGH; a single capped recovery has to
        be able to cross back over it. Tuning either value without checking
        the other would silently disable contraction.
        """
        levels = json.loads(
            (CONFIG / "confidence_policy.json").read_text(encoding="utf-8")
        )["levels"]
        limits = json.loads(
            (CONFIG / "runtime_signal_policy.json").read_text(encoding="utf-8")
        )["limits"]
        high_threshold = float(levels["HIGH"])
        credit_cap = float(limits["maximum_credit_per_reassessment"])

        eroded, _ = build_reassessor().reassess(
            baseline_confidence(),
            CONTRADICTION,
        )
        self.assertLess(
            eroded.confidence_score,
            high_threshold,
            "Erosion no longer drops confidence below HIGH; the expansion "
            "half of the demonstration is broken.",
        )
        self.assertGreaterEqual(
            eroded.confidence_score + credit_cap,
            high_threshold,
            "The credit cap is too small to restore HIGH confidence from an "
            "eroded state, so the planner can never contract again.",
        )

    def test_single_credit_signal_is_insufficient_to_contract(self):
        """Contraction requires accumulated resolving evidence, not one signal."""
        planner = build_planner()
        reassessor = build_reassessor()

        eroded, _ = reassessor.reassess(baseline_confidence(), CONTRADICTION)
        partial, _ = reassessor.reassess(
            eroded,
            [signal("KNOWLEDGE_CONTRADICTION_RESOLVED")],
        )
        self.assertEqual(
            planner.plan_from_confidence(partial).orchestration_mode,
            FULL,
        )


class ContractionGuardTests(unittest.TestCase):
    """High confidence alone must never be sufficient to narrow the plan."""

    def test_residual_contradiction_blocks_contraction(self):
        planner = build_planner()
        blocked = replace(baseline_confidence(), contradiction_level=0.35)
        self.assertEqual(
            planner.plan_from_confidence(blocked).orchestration_mode,
            FULL,
        )

    def test_eroding_drift_blocks_contraction(self):
        planner = build_planner()
        blocked = replace(baseline_confidence(), drift_status="ERODING")
        self.assertEqual(
            planner.plan_from_confidence(blocked).orchestration_mode,
            FULL,
        )

    def test_disallowed_hard_flag_blocks_contraction(self):
        planner = build_planner()
        blocked = replace(
            baseline_confidence(),
            hard_flags=["RECENT_HIGH_RISK_CHANGE"],
        )
        self.assertEqual(
            planner.plan_from_confidence(blocked).orchestration_mode,
            FULL,
        )

    def test_low_evidence_coverage_blocks_contraction(self):
        planner = build_planner()
        blocked = replace(baseline_confidence(), evidence_coverage=0.5)
        self.assertEqual(
            planner.plan_from_confidence(blocked).orchestration_mode,
            FULL,
        )


class ExecutionReachabilityTests(unittest.TestCase):
    """Contraction has to be reachable during a live execution, not just
    representable at the planner.

    The orchestrator reassesses confidence only after a skill named in the
    running mode's ``reassess_after_skills``. Without a hook on
    FULL_INVESTIGATION a run can widen but never narrow again, whatever
    evidence arrives.
    """

    def test_full_investigation_has_no_reassessment_hook_yet(self):
        modes = {
            mode["mode_id"]: mode
            for mode in json.loads(
                (CONFIG / "orchestration_policies.json").read_text(
                    encoding="utf-8"
                )
            )["modes"]
        }
        self.assertEqual(
            modes[ACCELERATED]["reassess_after_skills"],
            ["due_diligence_validation"],
        )
        self.assertEqual(
            modes[FULL]["reassess_after_skills"],
            [],
            "Recorded gap: without a hook here, contraction is provable at "
            "the planner but unreachable during execution.",
        )

    def test_reassessment_hooks_name_skills_the_mode_actually_runs(self):
        for mode in json.loads(
            (CONFIG / "orchestration_policies.json").read_text(encoding="utf-8")
        )["modes"]:
            for skill in mode["reassess_after_skills"]:
                self.assertIn(
                    skill,
                    mode["required_skills"],
                    f"{mode['mode_id']} reassesses after {skill}, which it "
                    f"never executes.",
                )

    def test_reassessment_hook_leaves_work_available_to_cancel(self):
        """A hook on the final skill of a plan could never change anything."""
        for mode in json.loads(
            (CONFIG / "orchestration_policies.json").read_text(encoding="utf-8")
        )["modes"]:
            for skill in mode["reassess_after_skills"]:
                position = mode["required_skills"].index(skill)
                self.assertLess(
                    position,
                    len(mode["required_skills"]) - 1,
                    f"{mode['mode_id']} reassesses after its last skill, so a "
                    f"revised plan would have nothing left to change.",
                )


class AsymmetricRatchetTests(unittest.TestCase):
    def test_recovery_never_restores_baseline_confidence(self):
        reassessor = build_reassessor()
        base = baseline_confidence()

        eroded, _ = reassessor.reassess(base, CONTRADICTION)
        recovered, _ = reassessor.reassess(eroded, RESOLUTION)

        self.assertLess(recovered.confidence_score, base.confidence_score)

    def test_repeated_contradiction_cycles_exhaust_the_accelerated_path(self):
        """The ratchet is the point: cycles cost more than they return.

        Each contradiction costs 0.22 while each recovery returns at most
        0.10, so a service that keeps producing contradictory evidence
        eventually cannot qualify for the accelerated plan again.
        """
        planner = build_planner()
        reassessor = build_reassessor()

        confidence = baseline_confidence()
        modes_after_recovery = []
        for _ in range(3):
            confidence, _ = reassessor.reassess(confidence, CONTRADICTION)
            confidence, _ = reassessor.reassess(confidence, RESOLUTION)
            modes_after_recovery.append(
                planner.plan_from_confidence(confidence).orchestration_mode
            )

        self.assertEqual(modes_after_recovery[0], ACCELERATED)
        self.assertEqual(modes_after_recovery[-1], FULL)
        self.assertLess(confidence.confidence_score, baseline_confidence().confidence_score)


if __name__ == "__main__":
    unittest.main()
