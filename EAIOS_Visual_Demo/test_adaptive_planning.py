from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import unittest

from adaptive_planner import AdaptivePlanner
from demo_adaptive_planning import build_planner
from operational_confidence_engine import OperationalConfidenceEngine
from skill_resolver import SkillResolver


ROOT = Path(__file__).resolve().parent


class AdaptivePlanningTests(unittest.TestCase):
    def test_payment_selects_three_agent_accelerated_plan(self):
        plan = build_planner().plan("SCN-PAY-001")
        self.assertEqual(plan.orchestration_mode, "ACCELERATED_VALIDATION")
        self.assertEqual(plan.confidence_level, "HIGH")
        self.assertEqual(plan.reasoning_agent_count, 3)
        self.assertEqual(
            plan.required_skills,
            [
                "semantic_context",
                "due_diligence_validation",
                "governed_recommendation",
            ],
        )
        self.assertTrue(plan.reassessment_required)
        self.assertEqual(plan.expansion_mode, "FULL_INVESTIGATION")

    def test_queue_selects_five_agent_full_investigation(self):
        plan = build_planner().plan("SCN-QUEUE-001")
        self.assertEqual(plan.orchestration_mode, "FULL_INVESTIGATION")
        # Band label is evidence-dependent; the plan choice is the behaviour.
        self.assertIn(plan.confidence_level, {"LOW", "MEDIUM"})
        self.assertEqual(plan.reasoning_agent_count, 5)
        self.assertIn("RECENT_HIGH_RISK_CHANGE", plan.hard_flags)

    def test_expected_result_fields_do_not_drive_planner(self):
        with TemporaryDirectory() as directory:
            json_copy = Path(directory) / "json"
            shutil.copytree(ROOT / "json", json_copy)
            scenario_file = json_copy / "scenarios.json"
            scenarios = json.loads(scenario_file.read_text(encoding="utf-8"))
            for row in scenarios:
                if row["scenario_id"] == "SCN-PAY-001":
                    row["expected_strategy"] = "Full Investigation"
                    row["expected_confidence"] = "LOW"
            scenario_file.write_text(
                json.dumps(scenarios, indent=2),
                encoding="utf-8",
            )
            plan = build_planner(json_copy).plan("SCN-PAY-001")
            self.assertEqual(
                plan.orchestration_mode,
                "ACCELERATED_VALIDATION",
            )
            self.assertEqual(plan.confidence_level, "HIGH")

    def test_new_failure_data_erodes_confidence_without_code_change(self):
        baseline = build_planner().plan("SCN-PAY-001")
        self.assertEqual(
            baseline.orchestration_mode,
            "ACCELERATED_VALIDATION",
        )

        with TemporaryDirectory() as directory:
            json_copy = Path(directory) / "json"
            shutil.copytree(ROOT / "json", json_copy)
            outcome_file = json_copy / "outcome_history.json"
            outcomes = json.loads(outcome_file.read_text(encoding="utf-8"))
            for index in range(1, 9):
                outcomes.append(
                    {
                        "outcome_id": f"TEST-DRIFT-{index:03d}",
                        "known_error_id": "KE-PAY-001",
                        "scenario_pattern": "PAYMENT_TIMEOUT",
                        "entity_id": "COMP-PAY-CONNECTOR",
                        "recommendation": "Existing recommendation",
                        "approval_decision": "Approved",
                        "human_modification": "None",
                        "action_performed": "Existing action",
                        "outcome": "Failed",
                        "recovery_minutes": 90,
                        "recurrence_within_24h": True,
                        "prior_confidence": "HIGH",
                        "evidence_usefulness_score": 35,
                        "recorded_at": f"2026-07-{15 + index:02d} 12:00:00",
                        "data_classification": "SYNTHETIC",
                    }
                )
            outcome_file.write_text(
                json.dumps(outcomes, indent=2),
                encoding="utf-8",
            )

            eroded = build_planner(json_copy).plan(
                "SCN-PAY-001",
                as_of="2026-07-24 15:00:00",
            )
            self.assertEqual(eroded.confidence_trend, "ERODING")
            self.assertEqual(eroded.drift_status, "ERODING")
            self.assertEqual(
                eroded.orchestration_mode,
                "FULL_INVESTIGATION",
            )
            self.assertEqual(eroded.reasoning_agent_count, 5)

    def test_agent_count_emerges_from_registry(self):
        with TemporaryDirectory() as directory:
            registry_path = Path(directory) / "agent_registry.json"
            registry = json.loads(
                (ROOT / "config" / "agent_registry.json").read_text(
                    encoding="utf-8"
                )
            )
            registry["agents"].append(
                {
                    "agent_id": "combined_acceleration_agent",
                    "name": "Combined Acceleration Agent",
                    "status": "ACTIVE",
                    "skills": [
                        "due_diligence_validation",
                        "governed_recommendation",
                    ],
                    "reliability_score": 0.99,
                    "estimated_cost": 1.0,
                    "a2a_protocol": "LOCAL_A2A",
                    "mcp_tools": [],
                    "data_domains": [],
                }
            )
            registry_path.write_text(
                json.dumps(registry, indent=2),
                encoding="utf-8",
            )
            resolver = SkillResolver(
                ROOT / "config" / "skill_catalog.json",
                registry_path,
            )
            confidence = OperationalConfidenceEngine(
                ROOT / "json",
                ROOT / "config" / "confidence_policy.json",
            )
            planner = AdaptivePlanner(
                confidence,
                resolver,
                ROOT / "config" / "orchestration_policies.json",
            )
            plan = planner.plan("SCN-PAY-001")
            self.assertEqual(plan.reasoning_agent_count, 2)
            selected = {agent.agent_id for agent in plan.selected_agents}
            self.assertIn("combined_acceleration_agent", selected)
            self.assertIn("graph_context_agent", selected)

    def test_inactive_agent_is_not_selected(self):
        with TemporaryDirectory() as directory:
            registry_path = Path(directory) / "agent_registry.json"
            registry = json.loads(
                (ROOT / "config" / "agent_registry.json").read_text(
                    encoding="utf-8"
                )
            )
            for row in registry["agents"]:
                if row["agent_id"] == "due_diligence_agent":
                    row["status"] = "INACTIVE"
            registry_path.write_text(
                json.dumps(registry, indent=2),
                encoding="utf-8",
            )
            resolver = SkillResolver(
                ROOT / "config" / "skill_catalog.json",
                registry_path,
            )
            resolution = resolver.resolve(
                [
                    "semantic_context",
                    "due_diligence_validation",
                    "governed_recommendation",
                ]
            )
            self.assertIn(
                "due_diligence_validation",
                resolution.uncovered_skills,
            )
            selected = {agent.agent_id for agent in resolution.selected_agents}
            self.assertNotIn("due_diligence_agent", selected)

    def test_queue_outcome_drift_is_detected(self):
        assessment = build_planner().confidence_engine.assess(
            "SCN-QUEUE-001"
        )
        self.assertEqual(assessment.drift_status, "ERODING")
        self.assertEqual(assessment.confidence_trend, "ERODING")


if __name__ == "__main__":
    unittest.main()
