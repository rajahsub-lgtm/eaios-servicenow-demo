"""What the confidence engine and the evidence fusion agent must agree on.

Four faults of one shape have now been found: both layers independently
deriving the same judgement, on different data or different scales, and
reaching different answers. Every one produced a run where the plan was chosen
on one premise and served by a stage acting on another.

None was caught by the existing suite, because each layer is internally
correct. Only asserting that they *agree* catches this, and nothing did.

The rule these tests encode:

    The confidence engine owns operational judgement.
    Evidence fusion owns evidence explanation and adjudication.

A judgement made in the engine is passed to fusion, never re-derived there.
Where the two must both know something — what history counts, which patterns
are recallable — they must read it from one place and get one answer.

Several of these fail at the commit that introduces them. That is deliberate:
the gaps are recorded as executable facts rather than prose, and each phase of
the correction has a target that goes green.
"""

from datetime import datetime
from pathlib import Path
import ast
import unittest

from case_fingerprint import CaseFingerprinter
from evidence_fusion_agent import EvidenceFusionAgent
from operational_confidence_engine import OperationalConfidenceEngine


ROOT = Path(__file__).resolve().parent
JSON = ROOT / "json"
ASSESSED_AT = datetime(2026, 7, 1)

# Scenarios that reach a hypothesis through recorded experience. The
# documented and non-diagnosis paths are asserted in their own suites; here
# the subject is agreement about experience the system actually has.
EXPERIENCE_SCENARIOS = (
    "SCN-PAY-001",
    "SCN-QUEUE-001",
    "SCN-PAY-CONTRADICT-001",
    "SCN-PAY-RESOLVED-001",
    "SCN-CROSS-GATEWAY-001",
    "SCN-PAY-EU-001",
)


def engine() -> OperationalConfidenceEngine:
    return OperationalConfidenceEngine(
        JSON, ROOT / "config" / "confidence_policy.json"
    )


def fusion() -> EvidenceFusionAgent:
    return EvidenceFusionAgent(JSON)


class TheySelectTheSamePatternTests(unittest.TestCase):
    def test_every_experienced_scenario_leads_with_one_pattern(self):
        e, f = engine(), fusion()
        for scenario_id in EXPERIENCE_SCENARIOS:
            with self.subTest(scenario=scenario_id):
                self.assertEqual(
                    e.assess(scenario_id).selected_known_error_id,
                    f.analyze(scenario_id).leading_hypothesis.hypothesis_id,
                )


class TheyCountTheSameCasesTests(unittest.TestCase):
    """Over the same pattern, the same history.

    Fusion reported 20 occurrences at 0.55 success where the engine computed
    0.47 over the same rows, because the engine weights by recency and
    provenance and fusion counted raw. The number a human reads was not the
    number that chose the plan.
    """

    def test_the_case_count_matches(self):
        e, f = engine(), fusion()
        for scenario_id in EXPERIENCE_SCENARIOS:
            with self.subTest(scenario=scenario_id):
                pattern = e.assess(scenario_id).selected_known_error_id
                self.assertIsNotNone(pattern)
                profile = e._outcome_profile(
                    known_error_id=pattern, assessed_at=ASSESSED_AT
                )
                history = f.analyze(scenario_id).leading_hypothesis.outcome_history
                self.assertEqual(history.occurrences, profile.sample_size)

    def test_the_success_rate_matches(self):
        e, f = engine(), fusion()
        for scenario_id in EXPERIENCE_SCENARIOS:
            with self.subTest(scenario=scenario_id):
                pattern = e.assess(scenario_id).selected_known_error_id
                profile = e._outcome_profile(
                    known_error_id=pattern, assessed_at=ASSESSED_AT
                )
                history = f.analyze(scenario_id).leading_hypothesis.outcome_history
                self.assertAlmostEqual(
                    history.success_rate,
                    profile.weighted_success_rate,
                    places=2,
                    msg=(
                        "Fusion explains a success rate the engine did not use. "
                        "Whichever is right, a human cannot be shown one number "
                        "while another chose the plan."
                    ),
                )

    def test_provenance_weighting_reaches_both_layers(self):
        """Everything provenance established is invisible to fusion today."""
        e, f = engine(), fusion()
        pattern = "KE-VENDOR-SAAS-001"
        profile = e._outcome_profile(
            known_error_id=pattern, assessed_at=ASSESSED_AT
        )
        self.assertEqual(profile.provenance_mix["PEER_AGENT"], 10)
        rows = [
            row for row in f.outcomes if row.get("known_error_id") == pattern
        ]
        self.assertTrue(rows, "fusion cannot see this pattern's history at all")
        self.assertTrue(
            hasattr(f, "trust_policy") or hasattr(f, "experience"),
            "fusion has no access to the experience trust policy, so a peer "
            "finding and a firsthand outcome weigh the same in the "
            "explanation a human reads",
        )


class TheyAdmitTheSamePatternsTests(unittest.TestCase):
    """Admissibility is duplicated in both layers and has already diverged.

    Excluding provisional patterns in one layer and not the other made a
    learned pattern recallable by the planner and invisible to the explainer.
    """

    def test_the_admissibility_rule_is_not_duplicated(self):
        sources = {
            name: (ROOT / name).read_text(encoding="utf-8")
            for name in (
                "operational_confidence_engine.py",
                "evidence_fusion_agent.py",
            )
        }
        holders = [
            name
            for name, text in sources.items()
            if '"Provisional"' in text and "knowledge_status" in text
        ]
        self.assertLessEqual(
            len(holders),
            1,
            f"pattern admissibility is decided in {holders}; it is one rule "
            f"and belongs in one place",
        )

    def test_both_layers_consider_the_same_patterns(self):
        e, f = engine(), fusion()
        for scenario_id in EXPERIENCE_SCENARIOS:
            with self.subTest(scenario=scenario_id):
                assessment = e.assess(scenario_id)
                engine_seen = {
                    c.known_error_id
                    for c in assessment.candidate_assessments
                    if c.experience_class != "DOCUMENTED"
                }
                result = f.analyze(scenario_id)
                fusion_seen = {
                    h.hypothesis_id
                    for h in [result.leading_hypothesis]
                    + list(result.alternative_hypotheses)
                    if h.hypothesis_type
                    not in {"DOCUMENTED_NOT_EXPERIENCED", "CHANGE_CORRELATION"}
                }
                self.assertTrue(
                    engine_seen <= fusion_seen,
                    f"the planner considered {engine_seen - fusion_seen} that "
                    f"the explainer never saw",
                )


class TheyReadTheSamePastTests(unittest.TestCase):
    """A fixture one layer reads and the other does not is a divergent past.

    Fusion did not read runtime outcome feedback for the whole of its
    existence, so everything the system learned at runtime was visible to the
    planner and invisible to the explainer.
    """

    SHARED_FIXTURES = (
        "outcome_history.json",
        "runtime_outcome_feedback.json",
        "known_errors.json",
        "learned_patterns.json",
    )

    def _reads(self, module: str) -> str:
        return (ROOT / module).read_text(encoding="utf-8")

    def test_both_layers_read_every_shared_fixture(self):
        engine_source = self._reads("operational_confidence_engine.py")
        fusion_source = self._reads("evidence_fusion_agent.py")
        for fixture in self.SHARED_FIXTURES:
            with self.subTest(fixture=fixture):
                in_engine = fixture in engine_source
                in_fusion = fixture in fusion_source
                self.assertEqual(
                    in_engine,
                    in_fusion,
                    f"{fixture} is read by "
                    f"{'the engine' if in_engine else 'fusion'} only",
                )

    def test_refutations_are_not_read_by_documentation_alone(self):
        """A rejection lowers a document's support while a learned pattern
        built from that same cause is untouched."""
        readers = [
            path.name
            for path in ROOT.glob("*.py")
            if not path.name.startswith(("test_", "demo_"))
            and "refutation_ledger" in path.read_text(encoding="utf-8")
        ]
        self.assertIn("documented_reasoning.py", readers)
        self.assertTrue(
            {"operational_confidence_engine.py", "evidence_fusion_agent.py"}
            & set(readers),
            "refutations attenuate documents but not learned patterns",
        )


class ThresholdsAreStatedOnceTests(unittest.TestCase):
    def test_experience_sufficiency_has_one_definition(self):
        """Promotion fires at ten successful cases while
        minimum_outcome_sample is fifteen, so a pattern sheds its provisional
        penalty while still flagged as insufficiently evidenced."""
        import json

        confidence = json.loads(
            (ROOT / "config" / "confidence_policy.json").read_text(
                encoding="utf-8"
            )
        )
        trust = json.loads(
            (ROOT / "config" / "experience_trust_policy.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            int(confidence["thresholds"]["minimum_outcome_sample"]),
            int(
                trust["pattern_maturity"]["promotion"][
                    "minimum_successful_cases"
                ]
            ),
            "two policies disagree about when experience is enough",
        )


class NoJudgementIsMadeTwiceTests(unittest.TestCase):
    """Structural guard. The fault class, not any single instance."""

    JUDGEMENT_MARKERS = (
        "reconsult_below",
        "minimum_outcome_sample",
        "maximum_documented_confidence",
    )

    def test_a_threshold_is_interpreted_in_one_module(self):
        for marker in self.JUDGEMENT_MARKERS:
            holders = [
                path.name
                for path in ROOT.glob("*.py")
                if not path.name.startswith(("test_", "demo_"))
                and marker in path.read_text(encoding="utf-8")
            ]
            with self.subTest(threshold=marker):
                self.assertLessEqual(
                    len(holders),
                    2,
                    f"{marker} is interpreted in {holders}; a threshold read "
                    f"in several places is a judgement made in several places",
                )

    def test_fusion_does_not_re_derive_what_the_engine_decided(self):
        """Fusion once decided for itself whether recall was thin, on its own
        scale, and disagreed with the engine about the same pattern."""
        source = (ROOT / "evidence_fusion_agent.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        analyze = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "analyze"
        )
        self.assertIn(
            "reconsult_documentation",
            {arg.arg for arg in analyze.args.kwonlyargs},
            "the reconsultation decision must arrive from the engine",
        )


if __name__ == "__main__":
    unittest.main()
