"""Structural checks on the synthetic fixtures.

The demonstration data is inspected directly during walkthroughs, so it has
to hold up to reading. These tests guard identifier uniqueness and the
scenario references the orchestrator relies on.
"""

from collections import Counter
from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parent
JSON_DIR = ROOT / "json"

# Fixture file -> the field that uniquely identifies a row.
IDENTIFIER_FIELDS = {
    "telemetry_samples.json": "sample_id",
    "scenarios.json": "scenario_id",
    "runtime_evidence_events.json": "signal_id",
    "entities.json": "entity_id",
    "incidents.json": "incident_id",
    "problems.json": "problem_id",
    "changes.json": "change_id",
    "known_errors.json": "known_error_id",
    "knowledge_documents.json": "document_id",
    "metric_definitions.json": "metric_id",
    "outcome_history.json": "outcome_id",
    "vendor_advisories.json": "advisory_id",
}


def load(filename: str) -> list[dict]:
    rows = json.loads((JSON_DIR / filename).read_text(encoding="utf-8"))
    return rows if isinstance(rows, list) else []


class IdentifierUniquenessTests(unittest.TestCase):
    def test_row_identifiers_are_unique_within_each_fixture(self):
        for filename, field in IDENTIFIER_FIELDS.items():
            if not (JSON_DIR / filename).exists():
                continue
            with self.subTest(fixture=filename):
                values = [
                    row[field] for row in load(filename)
                    if isinstance(row, dict) and row.get(field)
                ]
                duplicates = sorted(
                    identifier
                    for identifier, count in Counter(values).items()
                    if count > 1
                )
                self.assertEqual(
                    duplicates,
                    [],
                    f"{filename} reuses {field}: {duplicates[:5]}",
                )

    def test_telemetry_sample_ids_do_not_span_scenarios(self):
        """A sample belongs to one scenario; sharing an id hides that."""
        owners: dict[str, set[str]] = {}
        for row in load("telemetry_samples.json"):
            identifier = row.get("sample_id")
            if identifier:
                owners.setdefault(identifier, set()).add(row.get("scenario_id"))
        shared = sorted(k for k, v in owners.items() if len(v) > 1)
        self.assertEqual(shared, [], f"sample_ids shared across scenarios: {shared[:5]}")


class ScenarioReferenceTests(unittest.TestCase):
    def test_every_scenario_has_telemetry(self):
        scenarios = {row["scenario_id"] for row in load("scenarios.json")}
        with_telemetry = {
            row.get("scenario_id") for row in load("telemetry_samples.json")
        }
        missing = sorted(scenarios - with_telemetry)
        self.assertEqual(
            missing,
            [],
            f"scenarios without telemetry samples: {missing}",
        )

    def test_runtime_events_reference_known_scenarios(self):
        scenarios = {row["scenario_id"] for row in load("scenarios.json")}
        for event in load("runtime_evidence_events.json"):
            scenario_id = event.get("scenario_id")
            if scenario_id is None:
                continue  # deliberately unscoped events apply everywhere
            with self.subTest(signal=event.get("signal_id")):
                self.assertIn(scenario_id, scenarios)

    def test_runtime_events_have_unique_ids_per_scenario(self):
        pairs = [
            (event.get("scenario_id"), event.get("signal_type"),
             event.get("discovered_after_skill"))
            for event in load("runtime_evidence_events.json")
        ]
        duplicates = sorted(
            str(pair) for pair, count in Counter(pairs).items() if count > 1
        )
        self.assertEqual(
            duplicates,
            [],
            f"a scenario emits the same signal twice after one skill: {duplicates}",
        )


if __name__ == "__main__":
    unittest.main()
