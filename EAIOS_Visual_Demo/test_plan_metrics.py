"""Plan width and agent participation are separate measurements.

The legacy pair is asymmetric by history: initial_agent_count is a plan
width while final_agent_count counts agents that executed. That asymmetry is
invisible under expansion and wrong under contraction, so the canonical
metrics measure each thing directly. The legacy fields keep their meaning so
the frozen V1 story does not move.
"""

from pathlib import Path
import csv
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"

STABLE = "SCN-PAY-001"
CONTRADICTION = "SCN-PAY-CONTRADICT-001"
RESOLVED = "SCN-PAY-RESOLVED-001"


def execute(scenario_id: str):
    return AdaptiveExecutionOrchestrator(ROOT).execute(
        correlation_id=f"TEST-{scenario_id}",
        scenario_id=scenario_id,
    )


class LegacyFieldsUnchangedTests(unittest.TestCase):
    def test_frozen_v1_contradiction_still_reports_three_to_six(self):
        assessment = execute(CONTRADICTION)
        self.assertEqual(assessment.initial_agent_count, 3)
        self.assertEqual(assessment.final_agent_count, 6)

    def test_legacy_final_count_still_means_agents_executed(self):
        for scenario in (STABLE, CONTRADICTION, RESOLVED):
            with self.subTest(scenario=scenario):
                assessment = execute(scenario)
                self.assertEqual(
                    assessment.final_agent_count,
                    assessment.unique_agents_executed,
                )


class CanonicalMetricTests(unittest.TestCase):
    def test_plan_width_is_not_derived_from_execution(self):
        """Contraction ends narrower than the agents it drew on."""
        assessment = execute(RESOLVED)
        self.assertEqual(assessment.final_plan_agent_count, 3)
        self.assertGreater(
            assessment.unique_agents_executed,
            assessment.final_plan_agent_count,
        )

    def test_peak_width_survives_a_round_trip(self):
        """A plan that returns to its starting width still reports the peak."""
        assessment = execute(RESOLVED)
        self.assertEqual(assessment.initial_plan_agent_count, 3)
        self.assertEqual(assessment.final_plan_agent_count, 3)
        self.assertEqual(assessment.peak_plan_agent_count, 5)

    def test_peak_equals_final_width_for_a_pure_expansion(self):
        assessment = execute(CONTRADICTION)
        self.assertEqual(assessment.peak_plan_agent_count, 5)
        self.assertEqual(assessment.final_plan_agent_count, 5)

    def test_unrevised_run_reports_one_width_everywhere(self):
        assessment = execute(STABLE)
        self.assertEqual(assessment.initial_plan_agent_count, 3)
        self.assertEqual(assessment.peak_plan_agent_count, 3)
        self.assertEqual(assessment.final_plan_agent_count, 3)
        self.assertEqual(assessment.unique_agents_executed, 3)

    def test_peak_is_never_below_either_endpoint(self):
        for scenario in (STABLE, CONTRADICTION, RESOLVED):
            with self.subTest(scenario=scenario):
                assessment = execute(scenario)
                self.assertGreaterEqual(
                    assessment.peak_plan_agent_count,
                    assessment.initial_plan_agent_count,
                )
                self.assertGreaterEqual(
                    assessment.peak_plan_agent_count,
                    assessment.final_plan_agent_count,
                )


class PlanSummaryExportTests(unittest.TestCase):
    def test_plan_summary_csv_is_written_for_every_assessment(self):
        path = OUTPUTS / "servicenow_plan_summary.csv"
        self.assertTrue(path.exists(), "run demo_servicenow_storytelling.py first")
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        by_id = {row["correlation_id"]: row for row in rows}
        self.assertIn("EAIOS-DEMO-RESOLVED-001", by_id)

        resolved = by_id["EAIOS-DEMO-RESOLVED-001"]
        self.assertEqual(resolved["initial_plan_agent_count"], "3")
        self.assertEqual(resolved["final_plan_agent_count"], "3")
        self.assertEqual(resolved["peak_plan_agent_count"], "5")
        self.assertIn("FULL_INVESTIGATION", resolved["plan_path"])

    def test_frozen_readiness_export_keeps_its_original_columns(self):
        """Canonical metrics live in their own artifact, not bolted on here."""
        path = OUTPUTS / "servicenow_automation_readiness.csv"
        with path.open(encoding="utf-8") as handle:
            columns = next(csv.reader(handle))
        self.assertEqual(
            columns,
            [
                "correlation_id",
                "scenario",
                "confidence_score",
                "confidence_level",
                "drift_status",
                "automation_readiness",
                "human_approval_enforced",
                "blockers",
                "required_constraints",
                "explanation",
            ],
        )


if __name__ == "__main__":
    unittest.main()
