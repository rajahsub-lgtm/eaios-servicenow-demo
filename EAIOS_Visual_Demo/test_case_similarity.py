"""Experience is retrieved by presentation, not by label.

Applicability used to be a boolean graph reachability test, which produced two
opposite errors: a familiar component showing an unfamiliar symptom matched
confidently, and an identical symptom on a structural sibling did not match at
all. One is anchoring, the other is a failure to generalise.

These tests pin the ordering that separates them, and the ceiling that stops an
analogy ever counting as firsthand.
"""

from pathlib import Path
import json
import shutil
import tempfile
import unittest

from case_fingerprint import CaseFingerprinter, CaseFingerprint, severity_band
from case_similarity import CaseSimilarity


ROOT = Path(__file__).resolve().parent
POLICY = ROOT / "config" / "similarity_policy.json"

_fixture: list = []


def fixture() -> Path:
    """A sibling component and an unseen symptom, added to the real graph."""
    if _fixture:
        return _fixture[0]
    tmp = Path(tempfile.mkdtemp()) / "json"
    shutil.copytree(ROOT / "json", tmp)

    def load(name):
        return json.loads((tmp / name).read_text(encoding="utf-8"))

    def save(name, data):
        (tmp / name).write_text(json.dumps(data, indent=2), encoding="utf-8")

    entities = load("entities.json")
    entities.append({
        "entity_id": "COMP-PAY-CONNECTOR-EU", "entity_type": "SERVICE_COMPONENT",
        "name": "Payment Connector (EU)", "external_service_id": "SVC-ORDER-001",
        "environment": "Production", "owner": "Order Platform Team", "status": "ACTIVE",
        "description": "Regional connector of the same design as the primary.",
        "source_system": "Synthetic Enterprise Portfolio", "trust_level": "TRUSTED",
        "service_provider_type": "INTERNAL", "data_classification": "SYNTHETIC",
    })
    save("entities.json", entities)

    rels = load("semantic_relationships.json")
    n = max(int(r["relationship_id"].split("-")[1]) for r in rels) + 1
    for subject, predicate, obj in (
        ("AS-ORDER-MGMT", "DEPENDS_ON", "COMP-PAY-CONNECTOR-EU"),
        ("COMP-PAY-CONNECTOR-EU", "DEPENDS_ON", "AS-PAYMENT-GATEWAY"),
    ):
        rels.append({
            "relationship_id": f"REL-{n:03d}", "subject_entity_id": subject,
            "predicate": predicate, "object_entity_id": obj, "direction": "OUTBOUND",
            "relationship_authority": "AUTHORITATIVE", "confidence": 1.0,
            "valid_from": "2026-01-01 00:00:00", "valid_to": "", "status": "ACTIVE",
            "source_system": "Synthetic Enterprise Architecture",
            "provenance": "Service decomposition", "data_classification": "SYNTHETIC",
        })
        n += 1
    save("semantic_relationships.json", rels)

    metrics = load("metric_definitions.json")
    metrics.append({
        "metric_id": "MET-CONFIG-DRIFT", "name": "Connector Config Drift Rate",
        "description": "Instances diverging from baseline configuration.",
        "unit": "percent", "aggregation": "5-minute average",
        "warning_threshold": 5.0, "critical_threshold": 10.0, "higher_is_worse": True,
        "owner": "Order Platform Team", "source_system": "Synthetic OpenTelemetry",
        "symptom_categories": ["CONFIG_DRIFT"], "data_classification": "SYNTHETIC",
    })
    save("metric_definitions.json", metrics)

    _fixture.append(tmp)
    return tmp


def remembered() -> CaseFingerprint:
    tmp = fixture()
    known = {
        row["known_error_id"]: row
        for row in json.loads((tmp / "known_errors.json").read_text(encoding="utf-8"))
    }
    return CaseFingerprinter(tmp).for_known_error(known["KE-PAY-001"])


def presented(entity_id: str, metric_id: str, value: float, threshold: float):
    return CaseFingerprinter(fixture()).for_observation({
        "entity_id": entity_id, "metric_id": metric_id,
        "current_value": value, "threshold_value": threshold,
    })


def score(entity_id: str, metric_id: str, value=9.0, threshold=5.0):
    return CaseSimilarity(POLICY).compare(
        presented(entity_id, metric_id, value, threshold), remembered()
    )


EXACT = ("COMP-PAY-CONNECTOR", "MET-PAY-TIMEOUT")
SIBLING = ("COMP-PAY-CONNECTOR-EU", "MET-PAY-TIMEOUT")
DIVERGENT = ("COMP-PAY-CONNECTOR", "MET-CONFIG-DRIFT")
UNRELATED = ("COMP-ORDER-QUEUE", "MET-CONFIG-DRIFT")


class OrderingTests(unittest.TestCase):
    def test_the_four_cases_rank_in_clinical_order(self):
        """Exact beats sibling beats divergent beats unrelated."""
        exact = score(*EXACT).score
        sibling = score(*SIBLING).score
        divergent = score(*DIVERGENT).score
        unrelated = score(*UNRELATED).score
        self.assertGreater(exact, sibling)
        self.assertGreater(sibling, divergent)
        self.assertGreater(divergent, unrelated)

    def test_presentation_outranks_location(self):
        """The anchoring fix, stated directly.

        An identical symptom elsewhere must inform more than a different
        symptom here. Weighted the other way, a familiar component attracts
        its familiar diagnosis regardless of what it is actually doing.
        """
        self.assertGreater(score(*SIBLING).score, score(*DIVERGENT).score)

    def test_an_unrelated_case_falls_below_the_floor(self):
        assessment = score(*UNRELATED)
        self.assertLess(assessment.score, CaseSimilarity(POLICY).floor)
        self.assertIn("BELOW_SIMILARITY_FLOOR", assessment.reasons)


class DirectVersusTransferredTests(unittest.TestCase):
    def test_only_the_exact_case_counts_as_firsthand(self):
        self.assertTrue(score(*EXACT).is_direct)
        for case in (SIBLING, DIVERGENT, UNRELATED):
            with self.subTest(case=case):
                self.assertFalse(score(*case).is_direct)

    def test_an_analogy_can_never_reach_firsthand_strength(self):
        ceiling = float(
            json.loads(POLICY.read_text(encoding="utf-8"))["transfer"][
                "maximum_transferred_similarity"
            ]
        )
        for case in (SIBLING, DIVERGENT, UNRELATED):
            with self.subTest(case=case):
                self.assertLessEqual(score(*case).score, ceiling)

    def test_transfer_is_labelled_as_transfer(self):
        self.assertIn("TRANSFERRED_EXPERIENCE", score(*SIBLING).reasons)
        self.assertIn("DIRECT_EXPERIENCE", score(*EXACT).reasons)

    def test_symptom_divergence_is_named_not_hidden(self):
        self.assertIn("SYMPTOM_DIVERGENCE", score(*DIVERGENT).reasons)
        self.assertIn("STRUCTURAL_SIBLING", score(*SIBLING).reasons)


class FingerprintTests(unittest.TestCase):
    def test_structural_siblings_share_a_position(self):
        primary = presented(*EXACT, 9.0, 5.0)
        sibling = presented(*SIBLING, 9.0, 5.0)
        self.assertEqual(primary.parent_services, sibling.parent_services)
        self.assertEqual(primary.depends_on, sibling.depends_on)
        self.assertNotEqual(primary.entity_id, sibling.entity_id)

    def test_unrelated_components_do_not(self):
        primary = presented(*EXACT, 9.0, 5.0)
        other = presented("COMP-ORDER-QUEUE", "MET-QUEUE-DEPTH", 900.0, 500.0)
        self.assertNotEqual(primary.depends_on, other.depends_on)

    def test_severity_is_banded_so_near_identical_cases_group(self):
        self.assertEqual(severity_band(9.0, 5.0, True), "SEVERE")
        self.assertEqual(severity_band(9.4, 5.0, True), "SEVERE")
        self.assertEqual(severity_band(50.0, 5.0, True), "EXTREME")
        self.assertEqual(severity_band(4.0, 5.0, True), "WITHIN_THRESHOLD")

    def test_a_fingerprint_records_business_reach(self):
        self.assertGreater(presented(*EXACT, 9.0, 5.0).blast_radius, 0)


class PolicyTests(unittest.TestCase):
    def test_weights_are_policy_not_code(self):
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        self.assertIn("dimension_weights", policy)
        self.assertAlmostEqual(sum(policy["dimension_weights"].values()), 1.0, places=3)

    def test_symptom_is_weighted_above_entity_identity(self):
        weights = json.loads(POLICY.read_text(encoding="utf-8"))["dimension_weights"]
        self.assertGreater(weights["symptom_overlap"], weights["same_entity"])


if __name__ == "__main__":
    unittest.main()
