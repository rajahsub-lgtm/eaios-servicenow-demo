"""An agent cannot widen itself by asking.

Governance that is only ever seen approving things is indistinguishable from
no governance. The vendor agent asks for the evidence its question could use —
vendor advisories and internal telemetry — and receives only what it is
registered for. The refusal is recorded, and the agent completes bounded
rather than failing, which is the difference between an agent that is bounded
and one that is broken.
"""

from pathlib import Path
import json
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"

SCENARIO = "SCN-CROSS-GATEWAY-001"
V1_SCENARIOS = ("SCN-PAY-001", "SCN-PAY-CONTRADICT-001", "SCN-PAY-RESOLVED-001")

_runs: dict = {}


def run(scenario_id: str = SCENARIO):
    if scenario_id not in _runs:
        _runs[scenario_id] = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id=f"TEST-REFUSAL-{scenario_id}",
            scenario_id=scenario_id,
        )
    return _runs[scenario_id]


def vendor_output(scenario_id: str = SCENARIO) -> dict:
    return run(scenario_id).skill_outputs["external_service_health"]


class RefusalTests(unittest.TestCase):
    def test_the_agent_asks_for_more_than_it_is_granted(self):
        output = vendor_output()
        self.assertEqual(
            output["requested_evidence_domains"],
            ["vendor_advisories", "telemetry_samples"],
        )
        self.assertEqual(output["granted_evidence_domains"], ["vendor_advisories"])

    def test_the_out_of_grant_request_is_refused(self):
        refused = vendor_output()["refused_evidence_domains"]
        self.assertEqual(len(refused), 1)
        self.assertEqual(refused[0]["data_domain"], "telemetry_samples")
        self.assertEqual(refused[0]["decision"], "DENY")
        self.assertEqual(refused[0]["policy_id"], "DATA-UNREGISTERED-DENY")
        self.assertTrue(refused[0]["reason"])

    def test_the_refusal_reaches_the_audit_log(self):
        assessment = run()
        self.assertEqual(assessment.policy_decision_counts.get("DENY"), 1)
        denials = [
            d for d in assessment.policy_decisions
            if (d["decision"] if isinstance(d, dict) else d.decision) == "DENY"
        ]
        self.assertEqual(len(denials), 1)

    def test_the_agent_completes_despite_the_refusal(self):
        """Bounded, not broken."""
        output = vendor_output()
        self.assertEqual(
            sorted(output["vendors_reporting_healthy"]), ["GitHub", "Microsoft"]
        )
        self.assertIn("external_service_health", run().completed_skills)

    def test_the_run_is_unaffected_by_the_refusal(self):
        assessment = run()
        self.assertTrue(assessment.contracted_during_execution)
        self.assertEqual(assessment.final_confidence_score, 0.898)
        self.assertTrue(
            assessment.automation_readiness["human_approval_enforced"]
        )


class BoundaryIsEnforcedNotOnlyIntendedTests(unittest.TestCase):
    def test_the_refused_domain_is_registered_to_another_agent(self):
        """The domain exists and is legitimate — just not for this agent."""
        registry = json.loads(
            (CONFIG / "agent_registry.json").read_text(encoding="utf-8")
        )
        owners = {
            agent["agent_id"]
            for agent in registry["agents"]
            if "telemetry_samples" in agent.get("data_domains", [])
        }
        self.assertIn("telemetry_analysis_agent", owners)
        self.assertNotIn("vendor_health_agent", owners)

    def test_the_vendor_agent_declares_only_its_own_domain(self):
        registry = json.loads(
            (CONFIG / "agent_registry.json").read_text(encoding="utf-8")
        )
        vendor = next(
            a for a in registry["agents"] if a["agent_id"] == "vendor_health_agent"
        )
        self.assertEqual(vendor["data_domains"], ["vendor_advisories"])

    def test_no_internal_telemetry_appears_in_the_vendor_output(self):
        payload = json.dumps(vendor_output())
        for internal in ("MET-GW-TLS-HANDSHAKE-FAIL", "COMP-SECURE-WEB-GATEWAY"):
            self.assertNotIn(internal, payload)


class V1UnaffectedTests(unittest.TestCase):
    def test_v1_scenarios_refuse_nothing(self):
        for scenario_id in V1_SCENARIOS:
            with self.subTest(scenario=scenario_id):
                counts = run(scenario_id).policy_decision_counts
                self.assertNotIn("DENY", counts)

    def test_every_scenario_still_escalates_the_assessment_write(self):
        for scenario_id in (SCENARIO, *V1_SCENARIOS):
            with self.subTest(scenario=scenario_id):
                self.assertEqual(
                    run(scenario_id).policy_decision_counts.get("ESCALATE"), 1
                )


if __name__ == "__main__":
    unittest.main()
