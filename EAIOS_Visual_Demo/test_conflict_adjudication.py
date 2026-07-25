"""Evidence is immutable; conclusions change through recorded decisions.

A conflict that was material when it was retrieved stays recorded that way
forever. If later evidence retires it, that is a separate governed act with
its own trigger, signals, and confidence effect. These tests hold the two
apart, because collapsing them would mean the platform quietly edits history
to agree with wherever it ended up.
"""

from pathlib import Path
import json
import unittest

from eaios_story_data import StoryRepository


ROOT = Path(__file__).resolve().parent

UNRESOLVED = "EAIOS-DEMO-CONTRADICTION-001"
RESOLVED = "EAIOS-DEMO-RESOLVED-001"
NO_CONFLICT = "EAIOS-DEMO-CROSS-GATEWAY-001"

_repo: list = []


def repo() -> StoryRepository:
    if not _repo:
        _repo.append(StoryRepository.load(ROOT))
    return _repo[0]


def only(correlation_id: str) -> dict:
    rows = repo().conflict_adjudications(correlation_id)
    assert len(rows) == 1, f"expected one conflict for {correlation_id}"
    return rows[0]


class EvidenceImmutabilityTests(unittest.TestCase):
    def test_the_retrieval_record_is_identical_in_both_scenarios(self):
        """Resolution must not edit the evidence it resolves."""
        unresolved = repo().material_conflicts(UNRESOLVED)[0]
        resolved = repo().material_conflicts(RESOLVED)[0]
        for field in (
            "source_id",
            "governance_decision",
            "material_contradiction",
            "trust_level",
            "corroboration_count",
        ):
            with self.subTest(field=field):
                self.assertEqual(unresolved[field], resolved[field])

    def test_a_resolved_conflict_still_records_itself_as_material(self):
        conflict = repo().material_conflicts(RESOLVED)[0]
        self.assertTrue(conflict["material_contradiction"])
        self.assertEqual(conflict["governance_decision"], "ACCEPTED_WITH_LIMITATIONS")

    def test_adjudication_never_appears_inside_the_evidence_record(self):
        payload = json.dumps(repo().material_conflicts(RESOLVED)[0])
        for term in ("adjudication", "RESOLVED", "resolved_by", "governed_event"):
            self.assertNotIn(term, payload)

    def test_the_original_status_is_preserved_in_the_adjudication(self):
        self.assertEqual(only(RESOLVED)["original_status"], "MATERIAL_AT_RETRIEVAL")
        self.assertEqual(
            only(RESOLVED)["original_disposition"], "ACCEPTED_WITH_LIMITATIONS"
        )


class ResolutionEventTests(unittest.TestCase):
    def test_the_resolution_is_a_separate_event_with_its_own_trigger(self):
        row = only(RESOLVED)
        self.assertEqual(row["adjudication"], "RESOLVED")
        self.assertEqual(row["detected_after_skill"], "due_diligence_validation")
        self.assertEqual(row["resolved_after_skill"], "change_dependency_investigation")
        self.assertNotEqual(row["detected_after_skill"], row["resolved_after_skill"])

    def test_the_resolution_names_the_signals_that_carried_it(self):
        signals = only(RESOLVED)["resolving_signals"]
        self.assertIn("KNOWLEDGE_CONTRADICTION_RESOLVED", signals)

    def test_the_resolution_records_its_confidence_effect(self):
        row = only(RESOLVED)
        self.assertEqual(row["level_before"], "MEDIUM")
        self.assertEqual(row["level_after"], "HIGH")
        self.assertGreater(row["confidence_after"], row["confidence_before"])

    def test_the_governed_event_is_named(self):
        self.assertEqual(
            only(RESOLVED)["governed_event"],
            "CREDIBLE_KNOWLEDGE_CONTRADICTION resolved",
        )


class UnresolvedConflictTests(unittest.TestCase):
    def test_a_conflict_without_a_resolver_stays_active(self):
        row = only(UNRESOLVED)
        self.assertEqual(row["adjudication"], "ACTIVE")
        self.assertEqual(
            row["governed_event"], "CREDIBLE_KNOWLEDGE_CONTRADICTION outstanding"
        )

    def test_an_active_conflict_claims_no_resolution_detail(self):
        row = only(UNRESOLVED)
        for field in ("resolved_after_skill", "resolved_by", "resolving_signals"):
            self.assertNotIn(field, row)


class ConflictCountTests(unittest.TestCase):
    def test_active_counts_exclude_resolved_conflicts(self):
        self.assertEqual(
            repo().conflict_counts(RESOLVED), {"active": 0, "resolved": 1, "total": 1}
        )

    def test_resolved_counts_exclude_outstanding_conflicts(self):
        self.assertEqual(
            repo().conflict_counts(UNRESOLVED), {"active": 1, "resolved": 0, "total": 1}
        )

    def test_a_scenario_without_conflicts_reports_nothing_either_way(self):
        self.assertEqual(
            repo().conflict_counts(NO_CONFLICT), {"active": 0, "resolved": 0, "total": 0}
        )
        self.assertEqual(repo().conflict_adjudications(NO_CONFLICT), [])

    def test_counts_always_reconcile(self):
        for correlation_id in repo().assessment_labels():
            with self.subTest(scenario=correlation_id):
                counts = repo().conflict_counts(correlation_id)
                self.assertEqual(
                    counts["active"] + counts["resolved"], counts["total"]
                )


if __name__ == "__main__":
    unittest.main()
