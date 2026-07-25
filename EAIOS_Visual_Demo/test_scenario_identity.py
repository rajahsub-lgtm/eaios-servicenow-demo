"""Scenario identity is declared; execution behaviour is observed.

Labels used to be inferred from whether a run expanded or contracted. That
conflates two different things: expansion and contraction describe how one
execution behaved, while identity describes what the scenario is about. Two
scenarios can contract for entirely unrelated reasons, so the inference stops
being usable exactly when more scenarios exist.
"""

from dataclasses import replace
from pathlib import Path
import json
import unittest

from eaios_story_data import StoryRepository


ROOT = Path(__file__).resolve().parent

STABLE = "EAIOS-DEMO-STABLE-001"
CONTRADICTION = "EAIOS-DEMO-CONTRADICTION-001"
RESOLVED = "EAIOS-DEMO-RESOLVED-001"
CROSS = "EAIOS-DEMO-CROSS-GATEWAY-001"

_repo: list = []


def repo() -> StoryRepository:
    if not _repo:
        _repo.append(StoryRepository.load(ROOT))
    return _repo[0]


class IdentityFromMetadataTests(unittest.TestCase):
    def test_every_scenario_declares_its_identity(self):
        rows = json.loads((ROOT / "json" / "scenarios.json").read_text(encoding="utf-8"))
        for row in rows:
            with self.subTest(scenario=row["scenario_id"]):
                for field in ("display_name", "short_label", "scenario_category"):
                    self.assertTrue(row.get(field), f"{field} missing")

    def test_labels_come_from_the_declared_display_name(self):
        labels = repo().assessment_labels()
        self.assertEqual(
            labels[CROSS], "GitHub and Teams — shared gateway dependency"
        )
        self.assertEqual(labels[STABLE], "Payment connector — stable evidence")

    def test_labels_remain_distinct(self):
        labels = repo().assessment_labels()
        self.assertEqual(len(set(labels.values())), len(labels))

    def test_identity_is_independent_of_execution_behaviour(self):
        """Two scenarios that both contract still read differently."""
        resolved = repo().get_assessment(RESOLVED)
        cross = repo().get_assessment(CROSS)
        self.assertTrue(resolved["contracted_during_execution"])
        self.assertTrue(cross["contracted_during_execution"])

        labels = repo().assessment_labels()
        self.assertNotEqual(labels[RESOLVED], labels[CROSS])

    def test_category_separates_scenarios_sharing_a_service(self):
        identities = {
            cid: repo().scenario_identity(repo().get_assessment(cid)["scenario_id"])
            for cid in (CONTRADICTION, RESOLVED)
        }
        self.assertEqual(
            identities[CONTRADICTION]["scenario_category"], "Confidence erosion"
        )
        self.assertEqual(
            identities[RESOLVED]["scenario_category"], "Confidence recovery"
        )


class IdentityFallbackTests(unittest.TestCase):
    def test_an_undeclared_scenario_still_produces_a_readable_label(self):
        bare = replace(repo(), scenario_metadata={})
        identity = bare.scenario_identity("SCN-CROSS-GATEWAY-001")
        self.assertEqual(identity["display_name"], "Cross Gateway 001")
        self.assertEqual(identity["scenario_category"], "")

    def test_a_partially_declared_scenario_falls_back_per_field(self):
        partial = replace(
            repo(),
            scenario_metadata={"SCN-PAY-001": {"short_label": "Only a short label"}},
        )
        identity = partial.scenario_identity("SCN-PAY-001")
        self.assertEqual(identity["short_label"], "Only a short label")
        self.assertEqual(identity["display_name"], "Pay 001")


class PairwiseComparisonTests(unittest.TestCase):
    EXPECTED_METRICS = [
        "Initial confidence",
        "Final confidence",
        "Initial plan width",
        "Peak plan width",
        "Final plan width",
        "Unique agents contributing",
        "Readiness state",
        "Approval status",
        "Active conflicts",
        "Resolved conflicts",
    ]

    def test_the_same_metrics_are_reported_for_every_scenario(self):
        for correlation_id in repo().assessment_labels():
            with self.subTest(scenario=correlation_id):
                self.assertEqual(
                    list(repo().comparison_metrics(correlation_id)),
                    self.EXPECTED_METRICS,
                )

    def test_comparison_returns_one_row_per_metric_and_two_columns(self):
        frame = repo().compare(CONTRADICTION, CROSS)
        self.assertEqual(list(frame["Metric"]), self.EXPECTED_METRICS)
        self.assertEqual(len(frame.columns), 3)

    def test_columns_are_named_after_the_scenarios_compared(self):
        labels = repo().assessment_labels()
        frame = repo().compare(STABLE, CROSS)
        self.assertIn(labels[STABLE], frame.columns)
        self.assertIn(labels[CROSS], frame.columns)

    def test_the_comparison_surfaces_the_contrast_that_matters(self):
        frame = repo().compare(CONTRADICTION, RESOLVED).set_index("Metric")
        labels = repo().assessment_labels()
        self.assertEqual(frame.loc["Active conflicts", labels[CONTRADICTION]], 1)
        self.assertEqual(frame.loc["Active conflicts", labels[RESOLVED]], 0)
        self.assertEqual(frame.loc["Resolved conflicts", labels[RESOLVED]], 1)

    def test_plan_width_and_participation_appear_as_separate_rows(self):
        frame = repo().compare(STABLE, CROSS).set_index("Metric")
        labels = repo().assessment_labels()
        self.assertEqual(frame.loc["Final plan width", labels[CROSS]], 4)
        self.assertEqual(frame.loc["Unique agents contributing", labels[CROSS]], 7)

    def test_approval_is_reported_for_both_sides(self):
        frame = repo().compare(STABLE, CROSS).set_index("Metric")
        for column in frame.columns:
            self.assertEqual(frame.loc["Approval status", column], "REQUESTED")


if __name__ == "__main__":
    unittest.main()
