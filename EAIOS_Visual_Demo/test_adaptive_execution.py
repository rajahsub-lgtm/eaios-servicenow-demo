from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from policy_layer import (
    MCPEnforcementPoint,
    PolicyDecisionPoint,
    PolicyEnforcementError,
    PolicyRequest,
)


ROOT = Path(__file__).resolve().parent


class AdaptiveExecutionTests(unittest.TestCase):
    def test_stable_payment_executes_three_reasoning_agents(self):
        result = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id="TEST-ADAPT-PAY-001",
            scenario_id="SCN-PAY-001",
        )
        self.assertEqual(result.initial_plan_mode, "ACCELERATED_VALIDATION")
        self.assertEqual(result.final_plan_mode, "ACCELERATED_VALIDATION")
        self.assertFalse(result.expanded_during_execution)
        self.assertEqual(result.reasoning_agent_execution_count, 3)
        self.assertEqual(
            result.completed_skills,
            [
                "semantic_context",
                "due_diligence_validation",
                "governed_recommendation",
            ],
        )
        self.assertEqual(result.final_confidence_level, "HIGH")

    def test_queue_executes_five_reasoning_agents(self):
        result = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id="TEST-ADAPT-QUEUE-001",
            scenario_id="SCN-QUEUE-001",
        )
        self.assertEqual(result.initial_plan_mode, "FULL_INVESTIGATION")
        self.assertEqual(result.final_plan_mode, "FULL_INVESTIGATION")
        self.assertEqual(result.reasoning_agent_execution_count, 5)
        # Weak outcome history keeps this below the accelerated band; which
        # sub-band it lands in depends on the evidence, not the behaviour.
        self.assertIn(result.final_confidence_level, {"LOW", "MEDIUM"})

    def test_runtime_evidence_expands_accelerated_plan(self):
        with TemporaryDirectory() as directory:
            json_copy = Path(directory) / "json"
            shutil.copytree(ROOT / "json", json_copy)
            events = [
                {
                    "signal_id": "TEST-RUNTIME-CHANGE",
                    "signal_type": "RECENT_HIGH_RISK_CHANGE",
                    "entity_id": "COMP-PAY-CONNECTOR",
                    "discovered_after_skill": "due_diligence_validation",
                    "source_system": "Test",
                    "description": "New change discovered during due diligence.",
                    "data_classification": "SYNTHETIC",
                    "provenance": "Test approved structured record.",
                }
            ]
            (json_copy / "runtime_evidence_events.json").write_text(
                json.dumps(events, indent=2),
                encoding="utf-8",
            )
            result = AdaptiveExecutionOrchestrator(
                ROOT,
                json_dir=json_copy,
            ).execute(
                correlation_id="TEST-ADAPT-EXPAND-001",
                scenario_id="SCN-PAY-001",
            )
            self.assertEqual(
                result.initial_plan_mode,
                "ACCELERATED_VALIDATION",
            )
            self.assertEqual(
                result.final_plan_mode,
                "FULL_INVESTIGATION",
            )
            self.assertTrue(result.expanded_during_execution)
            self.assertEqual(result.final_confidence_level, "MEDIUM")
            self.assertIn(
                "detailed_telemetry_analysis",
                result.completed_skills,
            )
            self.assertIn(
                "governed_knowledge_retrieval",
                result.completed_skills,
            )
            self.assertNotIn(
                "governed_recommendation",
                result.completed_skills,
            )
            self.assertEqual(len(result.plan_transitions), 1)

    def test_policy_decisions_cover_a2a_mcp_and_data(self):
        result = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id="TEST-POLICY-COVERAGE",
            scenario_id="SCN-PAY-001",
        )
        request_types = {
            decision.request.request_type
            for decision in result.policy_decisions
        }
        self.assertEqual(request_types, {"A2A", "MCP", "DATA"})
        self.assertIn(
            "ALLOW_WITH_OBLIGATIONS",
            result.policy_decision_counts,
        )
        self.assertIn("ESCALATE", result.policy_decision_counts)

    def test_assessment_creation_is_escalated_for_approval(self):
        result = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id="TEST-ASSESSMENT-ESCALATE",
            scenario_id="SCN-PAY-001",
        )
        assessment_decisions = [
            decision for decision in result.policy_decisions
            if decision.request.resource_id == "servicenow.create_assessment"
        ]
        self.assertEqual(len(assessment_decisions), 1)
        self.assertEqual(assessment_decisions[0].decision, "ESCALATE")
        self.assertIn(
            "HUMAN_APPROVAL_BEFORE_ACTION",
            assessment_decisions[0].obligations,
        )

    def test_unregistered_agent_is_denied(self):
        pdp = PolicyDecisionPoint(
            ROOT / "config" / "access_policies.json",
            ROOT / "config" / "agent_registry.json",
            ROOT / "config" / "skill_catalog.json",
        )
        pep = MCPEnforcementPoint(pdp, [])
        bad = PolicyRequest(
            correlation_id="TEST-DENY",
            request_type="MCP",
            requesting_agent_id="unknown_agent",
            action="invoke_tool",
            resource_id="servicenow.query_recent_changes",
            skill_id="due_diligence_validation",
            operation_mode="READ",
            data_domain=None,
            data_classification="SYNTHETIC",
            purpose="operational_assessment",
        )
        with self.assertRaises(PolicyEnforcementError):
            pep.enforce(bad)

    def test_production_restart_is_escalated_not_executed(self):
        pdp = PolicyDecisionPoint(
            ROOT / "config" / "access_policies.json",
            ROOT / "config" / "agent_registry.json",
            ROOT / "config" / "skill_catalog.json",
        )
        pep = MCPEnforcementPoint(pdp, [])
        request = PolicyRequest(
            correlation_id="TEST-RESTART",
            request_type="MCP",
            requesting_agent_id="due_diligence_agent",
            action="invoke_tool",
            resource_id="production.restart",
            skill_id="due_diligence_validation",
            operation_mode="EXECUTE",
            data_domain=None,
            data_classification="SYNTHETIC",
            purpose="operational_assessment",
        )
        decision = pep.enforce(request)
        self.assertEqual(decision.decision, "ESCALATE")


if __name__ == "__main__":
    unittest.main()
