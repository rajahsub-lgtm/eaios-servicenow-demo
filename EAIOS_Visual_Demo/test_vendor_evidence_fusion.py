"""Vendor findings are evidence, and evidence retires hypotheses.

One agent establishing vendor health does not identify an internal cause, but
it does argue against the external explanation. That argument belongs in the
fusion record with its provenance, and the hypothesis it defeats must stay
visible with the reason it was defeated. A record showing only what survived
cannot be audited.
"""

from pathlib import Path
import json
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from evidence_fusion_agent import EvidenceFusionAgent
from vendor_health_agent import VendorHealthAgent


ROOT = Path(__file__).resolve().parent
JSON_DIR = ROOT / "json"
CONFIG = ROOT / "config"

SCENARIO = "SCN-CROSS-GATEWAY-001"
EXTERNAL = "KE-VENDOR-SAAS-001"
PLATFORM_ENTITIES = {
    "AS-GITHUB-ENTERPRISE", "COMP-GITHUB-REPO-ACCESS",
    "AS-TEAMS", "COMP-TEAMS-SIGNALING",
}

_cache: dict = {}


def vendor_health(entity_ids=None, required=("GitHub", "Microsoft")) -> dict:
    agent = VendorHealthAgent(JSON_DIR, CONFIG / "vendor_health_policy.json")
    assessment = agent.assess(
        scenario_id=SCENARIO,
        entity_ids=set(entity_ids or PLATFORM_ENTITIES),
        as_of="2026-07-16 08:35:00",
    )
    payload = VendorHealthAgent.to_dict(assessment)
    payload["required_vendor_dependencies"] = list(required)
    return payload


def fuse(vh=None):
    return EvidenceFusionAgent(JSON_DIR).analyze(SCENARIO, vendor_health=vh)


def run():
    if "run" not in _cache:
        _cache["run"] = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id="TEST-VENDOR-FUSION", scenario_id=SCENARIO
        )
    return _cache["run"]


def find(assessment, hypothesis_id):
    everything = [assessment.leading_hypothesis] + list(
        assessment.alternative_hypotheses
    )
    return next(h for h in everything if h.hypothesis_id == hypothesis_id)


class VendorEvidenceEntersTheLedgerTests(unittest.TestCase):
    def test_vendor_findings_appear_as_contributions(self):
        ledger = fuse(vendor_health()).evidence_ledger
        vendor = [e for e in ledger if e.evidence_type == "VENDOR_HEALTH"]
        self.assertEqual(len(vendor), 2)
        self.assertEqual({e.evidence_id for e in vendor},
                         {"VND-GITHUB-001", "VND-MSFT-001"})

    def test_vendor_contributions_carry_the_contradicts_role(self):
        ledger = fuse(vendor_health()).evidence_ledger
        for entry in [e for e in ledger if e.evidence_type == "VENDOR_HEALTH"]:
            with self.subTest(evidence=entry.evidence_id):
                self.assertEqual(entry.role, "CONTRADICTS")
                self.assertTrue(entry.provenance)
                self.assertGreater(entry.reliability, 0)

    def test_unusable_vendor_evidence_never_enters_the_ledger(self):
        """The stale advisory is retained by the vendor agent, not promoted."""
        ledger = fuse(vendor_health()).evidence_ledger
        self.assertNotIn(
            "VND-GITHUB-STALE-001", {e.evidence_id for e in ledger}
        )

    def test_the_ledger_argues_both_ways(self):
        roles = {e.role for e in fuse(vendor_health()).evidence_ledger}
        self.assertIn("SUPPORTS", roles)
        self.assertIn("CONTRADICTS", roles)


class HypothesisRetirementTests(unittest.TestCase):
    def test_the_external_hypothesis_is_retired_on_vendor_evidence(self):
        hypothesis = find(fuse(vendor_health()), EXTERNAL)
        self.assertEqual(hypothesis.status, "REJECTED")
        self.assertTrue(hypothesis.rejection_reason)
        self.assertEqual(
            set(hypothesis.contradicting_evidence_ids),
            {"VND-GITHUB-001", "VND-MSFT-001"},
        )

    def test_a_retired_hypothesis_keeps_its_place_in_the_record(self):
        """Rejected is not deleted. The candidate stays, scored and explained."""
        assessment = fuse(vendor_health())
        ids = {h.hypothesis_id for h in assessment.alternative_hypotheses}
        self.assertIn(EXTERNAL, ids)
        self.assertGreater(find(assessment, EXTERNAL).score, 0)

    def test_retirement_lowers_the_score_rather_than_hiding_it(self):
        before = find(fuse(), EXTERNAL).score
        after = find(fuse(vendor_health()), EXTERNAL).score
        self.assertLess(after, before)

    def test_ranking_never_revives_a_retired_hypothesis(self):
        for hypothesis in fuse(vendor_health()).alternative_hypotheses:
            if hypothesis.hypothesis_id == EXTERNAL:
                self.assertEqual(hypothesis.status, "REJECTED")

    def test_internal_hypotheses_are_untouched_by_vendor_evidence(self):
        """Healthy vendors say nothing about internal candidates."""
        with_vendor = fuse(vendor_health())
        without = fuse()
        for hypothesis_id in ("KE-GATEWAY-001", "KE-RUNNER-POOL-001"):
            with self.subTest(hypothesis=hypothesis_id):
                self.assertEqual(
                    find(with_vendor, hypothesis_id).score,
                    find(without, hypothesis_id).score,
                )


class PartialCoverageTests(unittest.TestCase):
    def test_partial_vendor_coverage_does_not_retire_the_hypothesis(self):
        """Half the evidence cannot retire a claim covering both vendors."""
        partial = vendor_health(
            entity_ids={"AS-GITHUB-ENTERPRISE", "COMP-GITHUB-REPO-ACCESS"},
            required=("GitHub", "Microsoft"),
        )
        hypothesis = find(fuse(partial), EXTERNAL)
        self.assertNotEqual(hypothesis.status, "REJECTED")
        self.assertEqual(hypothesis.rejection_reason, "")

    def test_no_vendor_evidence_leaves_every_hypothesis_standing(self):
        for hypothesis in fuse().alternative_hypotheses:
            with self.subTest(hypothesis=hypothesis.hypothesis_id):
                self.assertNotEqual(hypothesis.status, "REJECTED")


class LiveRunTests(unittest.TestCase):
    def test_the_retirement_reaches_the_recommendation(self):
        retired = run().recommendation["retired_hypotheses"]
        self.assertEqual(len(retired), 1)
        self.assertEqual(retired[0]["hypothesis_id"], EXTERNAL)
        self.assertTrue(retired[0]["rejection_reason"])

    def test_the_gateway_hypothesis_still_leads(self):
        self.assertEqual(
            run().recommendation["leading_hypothesis_id"], "KE-GATEWAY-001"
        )

    def test_contraction_and_approval_are_unaffected(self):
        assessment = run()
        self.assertTrue(assessment.contracted_during_execution)
        self.assertTrue(
            assessment.automation_readiness["human_approval_enforced"]
        )


class V1UnaffectedTests(unittest.TestCase):
    def test_v1_scenarios_retire_nothing(self):
        agent = EvidenceFusionAgent(JSON_DIR)
        for scenario_id in (
            "SCN-PAY-001", "SCN-QUEUE-001",
            "SCN-PAY-CONTRADICT-001", "SCN-PAY-RESOLVED-001",
        ):
            with self.subTest(scenario=scenario_id):
                assessment = agent.analyze(scenario_id)
                for hypothesis in assessment.alternative_hypotheses:
                    self.assertNotEqual(hypothesis.status, "REJECTED")

    def test_v1_ledgers_contain_no_vendor_evidence(self):
        agent = EvidenceFusionAgent(JSON_DIR)
        for scenario_id in ("SCN-PAY-001", "SCN-PAY-CONTRADICT-001"):
            with self.subTest(scenario=scenario_id):
                types = {
                    e.evidence_type
                    for e in agent.analyze(scenario_id).evidence_ledger
                }
                self.assertNotIn("VENDOR_HEALTH", types)


if __name__ == "__main__":
    unittest.main()
