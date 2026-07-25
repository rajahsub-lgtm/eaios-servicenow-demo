from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from adaptive_servicenow_mapper import AdaptiveServiceNowMapper, ServiceNowMappingError
from demo_servicenow_boundary import InMemoryTableClient, confirmed_test_mapping
from demo_adaptive_planning import build_planner
from outcome_feedback import OutcomeFeedbackStore, OutcomeInput, feedback_from_assessment
from servicenow_field_discovery import build_suggestions
from servicenow_repository import ServiceNowAssessmentRepository


ROOT = Path(__file__).resolve().parent


class ServiceNowBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assessment = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id="TEST-SNOW-ASSESSMENT",
            scenario_id="SCN-PAY-001",
        )

    def test_reviewed_mapping_produces_live_payload(self):
        mapper = AdaptiveServiceNowMapper(
            ROOT / "config" / "servicenow_field_mapping.json"
        )
        payload = mapper.map_for_live(self.assessment)
        self.assertEqual(payload["u_correlation_id"], "TEST-SNOW-ASSESSMENT")
        self.assertEqual(payload["approval"], "requested")
        self.assertEqual(payload["u_outcome"], "Pending")

    def test_dry_run_includes_mapped_payload(self):
        mapper = AdaptiveServiceNowMapper(
            ROOT / "config" / "servicenow_field_mapping.json"
        )
        preview = mapper.dry_run_preview(self.assessment)
        self.assertEqual(preview["mode"], "DRY_RUN")
        self.assertEqual(
            preview["conceptual_values"]["Correlation ID"],
            "TEST-SNOW-ASSESSMENT",
        )
        self.assertEqual(
            preview["mapped_servicenow_payload"]["approval"],
            "requested",
        )
        self.assertFalse(preview["live_write_blocked"])

    def test_exact_label_discovery_suggests_but_does_not_confirm(self):
        mapping = json.loads(
            (ROOT / "config" / "servicenow_field_mapping.json").read_text(
                encoding="utf-8"
            )
        )
        mapping["fields"]["Correlation ID"]["internal_name"] = None
        mapping["fields"]["Correlation ID"]["confirmed"] = False
        discovered = [
            {"element":"u_correlation_id","column_label":"Correlation ID","internal_type":"string"},
            {"element":"u_selected_strategy","column_label":"Selected strategy","internal_type":"string"},
        ]
        suggestion = build_suggestions(mapping, discovered)
        self.assertEqual(
            suggestion["fields"]["Correlation ID"]["suggested_internal_name"],
            "u_correlation_id",
        )
        self.assertFalse(suggestion["fields"]["Correlation ID"]["confirmed"])

    def test_correlation_upsert_creates_then_updates(self):
        with TemporaryDirectory() as directory:
            mapping_path = Path(directory) / "mapping.json"
            confirmed_test_mapping(mapping_path)
            mapper = AdaptiveServiceNowMapper(mapping_path)
            payload = mapper.map_for_live(self.assessment)
            client = InMemoryTableClient()
            repo = ServiceNowAssessmentRepository(client, mapper.target_table, mapper.correlation_field)
            first = repo.upsert(self.assessment.correlation_id, payload)
            second = repo.upsert(self.assessment.correlation_id, payload)
            self.assertEqual(first.action, "CREATED")
            self.assertEqual(second.action, "UPDATED")
            self.assertEqual(first.sys_id, second.sys_id)
            self.assertEqual(len(client.records), 1)

    def test_feedback_store_is_idempotent(self):
        with TemporaryDirectory() as directory:
            store = OutcomeFeedbackStore(Path(directory) / "feedback.json")
            feedback = feedback_from_assessment(
                self.assessment,
                OutcomeInput(
                    approval_decision="Approved",
                    human_modification="None",
                    action_performed="Validation",
                    outcome="Successful",
                    recovery_minutes=20,
                    recurrence_within_24h=False,
                    evidence_usefulness_score=90,
                    recorded_at="2026-07-16 12:00:00",
                ),
                outcome_id="OUT-TEST-IDEMPOTENT",
            )
            self.assertTrue(store.append(feedback))
            self.assertFalse(store.append(feedback))
            self.assertEqual(len(store.list()), 1)

    def test_runtime_feedback_changes_future_plan(self):
        with TemporaryDirectory() as directory:
            json_copy = Path(directory) / "json"
            shutil.copytree(ROOT / "json", json_copy)
            assessment = AdaptiveExecutionOrchestrator(ROOT, json_dir=json_copy).execute(
                correlation_id="TEST-FEEDBACK-PLAN",
                scenario_id="SCN-PAY-001",
            )
            store = OutcomeFeedbackStore(json_copy / "runtime_outcome_feedback.json")
            for index in range(8):
                store.append(feedback_from_assessment(
                    assessment,
                    OutcomeInput(
                        approval_decision="Approved",
                        human_modification="Expanded",
                        action_performed="Restart",
                        outcome="Failed",
                        recovery_minutes=90,
                        recurrence_within_24h=True,
                        evidence_usefulness_score=30,
                        recorded_at=f"2026-07-{16+index:02d} 12:00:00",
                    ),
                    outcome_id=f"OUT-TEST-FEEDBACK-{index}",
                ))
            changed = build_planner(json_copy).plan(
                "SCN-PAY-001", as_of="2026-07-24 15:00:00"
            )
            self.assertEqual(changed.orchestration_mode, "FULL_INVESTIGATION")
            self.assertEqual(changed.drift_status, "ERODING")


if __name__ == "__main__":
    unittest.main()
