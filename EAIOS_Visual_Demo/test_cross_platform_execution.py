"""The cross-platform scenario, end to end.

Two platforms fail, each vendor reports itself healthy, traversal finds what
they share, and the plan narrows onto the internal cause. Approval stays with
ServiceNow throughout: the run proposes, it never authorises.
"""

from pathlib import Path
import json
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from servicenow_sync import known_scenario_ids


ROOT = Path(__file__).resolve().parent
JSON_DIR = ROOT / "json"

SCENARIO = "SCN-CROSS-GATEWAY-001"
V1_SCENARIOS = ("SCN-PAY-001", "SCN-PAY-CONTRADICT-001", "SCN-PAY-RESOLVED-001")

_cache: dict = {}


def run(scenario_id: str = SCENARIO):
    if scenario_id not in _cache:
        _cache[scenario_id] = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id=f"TEST-{scenario_id}",
            scenario_id=scenario_id,
        )
    return _cache[scenario_id]


class DiscoveryTests(unittest.TestCase):
    def test_execution_reaches_the_second_platform_from_the_first(self):
        context = run().skill_outputs["semantic_context"]
        entities = set(context["authoritative_entity_ids"])
        self.assertIn("COMP-GITHUB-REPO-ACCESS", entities)
        self.assertIn("COMP-TEAMS-SIGNALING", entities)

    def test_execution_reaches_the_shared_dependency_and_its_configuration(self):
        entities = set(run().skill_outputs["semantic_context"]["authoritative_entity_ids"])
        self.assertIn("COMP-SECURE-WEB-GATEWAY", entities)
        self.assertIn("COMP-GATEWAY-TLS-POLICY", entities)

    def test_the_scenario_does_not_name_its_own_answer(self):
        """The trigger points at GitHub; the gateway is reached, not declared."""
        scenarios = json.loads((JSON_DIR / "scenarios.json").read_text(encoding="utf-8"))
        row = next(s for s in scenarios if s["scenario_id"] == SCENARIO)
        self.assertEqual(row["primary_component_id"], "COMP-GITHUB-REPO-ACCESS")
        self.assertNotIn("GATEWAY", row["primary_component_id"])
        self.assertNotIn("COMP-SECURE-WEB-GATEWAY", json.dumps(row))


class VendorBoundaryTests(unittest.TestCase):
    def test_both_vendors_are_required_and_established(self):
        vendor = run().skill_outputs["external_service_health"]
        self.assertEqual(vendor["required_vendor_dependencies"], ["GitHub", "Microsoft"])
        self.assertEqual(sorted(vendor["vendors_reporting_healthy"]), ["GitHub", "Microsoft"])

    def test_both_external_hypotheses_are_retired(self):
        vendor = run().skill_outputs["external_service_health"]
        self.assertEqual(
            sorted(vendor["eliminated_external_hypotheses"]),
            ["EXTERNAL_GITHUB_OUTAGE", "EXTERNAL_MICROSOFT_OUTAGE"],
        )

    def test_unusable_evidence_is_retained_not_discarded(self):
        findings = run().skill_outputs["external_service_health"]["findings"]
        stale = next(f for f in findings if f["advisory_id"] == "VND-GITHUB-STALE-001")
        self.assertFalse(stale["eliminates_external_hypothesis"])
        self.assertIn("STALE_BEYOND_FRESHNESS_WINDOW", stale["disqualification_reasons"])


class OrderingTests(unittest.TestCase):
    def test_vendor_health_runs_before_the_reassessment_that_uses_it(self):
        order = [t.skill_id for t in run().execution_trace]
        self.assertLess(
            order.index("external_service_health"),
            order.index("change_dependency_investigation"),
        )

    def test_the_reassessment_weighs_the_vendor_signals(self):
        record = run().skill_outputs["confidence_reassessments"][
            "change_dependency_investigation"
        ]
        self.assertIn("VENDOR_STATUS_CONFIRMED", record["runtime_signal_types"])
        self.assertIn("EXTERNAL_HYPOTHESIS_ELIMINATED", record["runtime_signal_types"])
        self.assertEqual(record["resolved_hard_flags"], ["VENDOR_STATUS_UNKNOWN"])


class ContractionTests(unittest.TestCase):
    def test_the_plan_starts_wide_and_narrows(self):
        assessment = run()
        self.assertEqual(assessment.initial_plan_mode, "FULL_INVESTIGATION")
        self.assertEqual(assessment.final_plan_mode, "ACCELERATED_VALIDATION")
        self.assertTrue(assessment.contracted_during_execution)
        self.assertFalse(assessment.expanded_during_execution)

    def test_the_transition_is_recorded_as_a_contraction(self):
        transitions = run().plan_transitions
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].direction, "CONTRACTION")
        self.assertEqual(
            transitions[0].triggered_after_skill, "change_dependency_investigation"
        )

    def test_cancelled_work_never_executes(self):
        assessment = run()
        cancelled = assessment.plan_transitions[0].cancelled_skills
        self.assertIn("evidence_fusion_recommendation", cancelled)
        for skill in cancelled:
            self.assertNotIn(skill, assessment.completed_skills)
            self.assertNotIn(skill, assessment.skill_outputs)

    def test_completed_evidence_survives_the_contraction(self):
        assessment = run()
        for skill in (
            "semantic_context",
            "detailed_telemetry_analysis",
            "governed_knowledge_retrieval",
            "external_service_health",
            "change_dependency_investigation",
        ):
            with self.subTest(skill=skill):
                self.assertIn(skill, assessment.completed_skills)
                self.assertIn(skill, assessment.skill_outputs)

    def test_the_narrower_plan_supplies_the_recommendation(self):
        assessment = run()
        self.assertIn("governed_recommendation", assessment.completed_skills)
        self.assertTrue(assessment.recommendation)

    def test_plan_width_and_participation_are_reported_separately(self):
        assessment = run()
        self.assertLess(
            assessment.final_plan_agent_count, assessment.initial_plan_agent_count
        )
        self.assertGreater(
            assessment.unique_agents_executed, assessment.final_plan_agent_count
        )
        self.assertEqual(
            assessment.peak_plan_agent_count, assessment.initial_plan_agent_count
        )

    def test_recovered_confidence_respects_the_runtime_ceiling(self):
        assessment = run()
        limits = json.loads(
            (ROOT / "config" / "runtime_signal_policy.json").read_text(encoding="utf-8")
        )["limits"]
        self.assertGreater(
            assessment.final_confidence_score, assessment.initial_confidence_score
        )
        self.assertLessEqual(
            assessment.final_confidence_score,
            float(limits["maximum_runtime_confidence"]),
        )


class ApprovalBoundaryTests(unittest.TestCase):
    """Approval is ServiceNow's to give. The run only ever proposes."""

    def test_human_approval_stays_mandatory_despite_recovered_confidence(self):
        assessment = run()
        self.assertEqual(assessment.final_confidence_level, "HIGH")
        self.assertTrue(assessment.automation_readiness["human_approval_enforced"])
        self.assertEqual(assessment.safety_status, "REQUIRES_HUMAN_APPROVAL")

    def test_readiness_never_claims_the_action_is_authorised(self):
        self.assertNotEqual(run().automation_readiness["status"], "APPROVED")

    def test_the_scenario_is_reachable_from_the_servicenow_cli(self):
        self.assertIn(SCENARIO, known_scenario_ids())


class V1RegressionTests(unittest.TestCase):
    def test_v1_scenarios_keep_their_story(self):
        """Shape, not values. Experience transfer moves the numbers on purpose."""
        stable = run("SCN-PAY-001")
        self.assertEqual(
            stable.final_confidence_score, stable.initial_confidence_score
        )
        self.assertEqual(stable.automation_readiness["status"], "CANDIDATE")

        eroded = run("SCN-PAY-CONTRADICT-001")
        self.assertLess(
            eroded.final_confidence_score, eroded.initial_confidence_score
        )
        self.assertEqual(eroded.automation_readiness["status"], "SUSPENDED")

        resolved = run("SCN-PAY-RESOLVED-001")
        self.assertGreater(
            resolved.final_confidence_score, eroded.final_confidence_score
        )
        self.assertLess(
            resolved.final_confidence_score, resolved.initial_confidence_score
        )
        self.assertEqual(
            resolved.automation_readiness["status"], "BUILDING_EVIDENCE"
        )

    def test_v1_scenarios_never_gather_vendor_evidence(self):
        for scenario_id in V1_SCENARIOS:
            with self.subTest(scenario=scenario_id):
                self.assertNotIn("external_service_health", run(scenario_id).skill_outputs)


class ScenarioDataTests(unittest.TestCase):
    def test_incidents_arrive_in_separate_support_groups(self):
        rows = json.loads((JSON_DIR / "incidents.json").read_text(encoding="utf-8"))
        mine = [r for r in rows if r.get("scenario_id") == SCENARIO]
        self.assertGreaterEqual(len(mine), 4)
        self.assertEqual(len({r["assignment_group"] for r in mine}), 2)

    def test_every_scenario_record_is_synthetic(self):
        for filename in ("incidents.json", "telemetry_samples.json",
                         "health_observations.json", "changes.json"):
            rows = json.loads((JSON_DIR / filename).read_text(encoding="utf-8"))
            for row in [r for r in rows if r.get("scenario_id") == SCENARIO]:
                with self.subTest(fixture=filename):
                    self.assertEqual(row["data_classification"], "SYNTHETIC")

    def test_telemetry_shows_recovery_after_the_change_is_reverted(self):
        rows = json.loads((JSON_DIR / "telemetry_samples.json").read_text(encoding="utf-8"))
        for metric in ("MET-GIT-AUTH-FAIL", "MET-TEAMS-JOIN-FAIL"):
            series = sorted(
                (r for r in rows if r.get("scenario_id") == SCENARIO
                 and r["metric_id"] == metric),
                key=lambda r: r["observed_at"],
            )
            with self.subTest(metric=metric):
                self.assertGreater(max(r["value"] for r in series), series[0]["value"])
                self.assertLessEqual(series[-1]["value"], series[0]["value"] * 2)

    def test_no_records_leak_between_scenarios(self):
        rows = json.loads((JSON_DIR / "telemetry_samples.json").read_text(encoding="utf-8"))
        entities = {
            r["entity_id"] for r in rows if r.get("scenario_id") == SCENARIO
        }
        self.assertNotIn("COMP-PAY-CONNECTOR", entities)
        self.assertNotIn("COMP-ORDER-QUEUE", entities)


if __name__ == "__main__":
    unittest.main()
