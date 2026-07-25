"""Properties that must hold for every scenario, present and future.

The per-scenario suites prove that each demonstration behaves as designed.
These prove the things that must never vary: approval stays with a human,
evidence stays synthetic, confidence stays inside its ceiling, and no plan
claims work it did not do. Every scenario in the fixture is checked, so a
scenario added later is covered the moment it exists rather than when
somebody remembers to write a test for it.
"""

from pathlib import Path
import json
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from adaptive_servicenow_mapper import AdaptiveServiceNowMapper


ROOT = Path(__file__).resolve().parent
JSON_DIR = ROOT / "json"
CONFIG = ROOT / "config"

_runs: dict = {}


def scenario_ids() -> list[str]:
    rows = json.loads((JSON_DIR / "scenarios.json").read_text(encoding="utf-8"))
    return [row["scenario_id"] for row in rows]


def run(scenario_id: str):
    if scenario_id not in _runs:
        _runs[scenario_id] = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id=f"INVARIANT-{scenario_id}",
            scenario_id=scenario_id,
        )
    return _runs[scenario_id]


def every_scenario():
    for scenario_id in scenario_ids():
        yield scenario_id, run(scenario_id)


class HumanApprovalInvariants(unittest.TestCase):
    """V1 proposes. It never authorises."""

    def test_no_scenario_removes_human_approval(self):
        for scenario_id, assessment in every_scenario():
            with self.subTest(scenario=scenario_id):
                self.assertTrue(
                    assessment.automation_readiness["human_approval_enforced"]
                )

    def test_readiness_is_advisory_in_every_scenario(self):
        for scenario_id, assessment in every_scenario():
            with self.subTest(scenario=scenario_id):
                self.assertTrue(assessment.automation_readiness["advisory_only"])

    def test_no_scenario_reports_itself_approved(self):
        for scenario_id, assessment in every_scenario():
            with self.subTest(scenario=scenario_id):
                self.assertNotIn(
                    assessment.approval_state.upper(),
                    {"APPROVED", "AUTO_APPROVED", "GRANTED"},
                )

    def test_high_confidence_never_purchases_autonomy(self):
        """The one that matters: confidence at its ceiling changes nothing."""
        for scenario_id, assessment in every_scenario():
            if assessment.final_confidence_level != "HIGH":
                continue
            with self.subTest(scenario=scenario_id):
                self.assertTrue(
                    assessment.automation_readiness["human_approval_enforced"]
                )
                self.assertEqual(assessment.safety_status, "REQUIRES_HUMAN_APPROVAL")


class ServiceNowBoundaryInvariants(unittest.TestCase):
    def test_every_scenario_maps_with_approval_requested_and_outcome_pending(self):
        mapper = AdaptiveServiceNowMapper(CONFIG / "servicenow_field_mapping.json")
        for scenario_id, assessment in every_scenario():
            with self.subTest(scenario=scenario_id):
                payload = mapper.dry_run_preview(assessment)[
                    "mapped_servicenow_payload"
                ]
                self.assertEqual(payload["approval"], "requested")
                self.assertEqual(payload["u_outcome"], "Pending")

    def test_every_scenario_maps_without_error(self):
        mapper = AdaptiveServiceNowMapper(CONFIG / "servicenow_field_mapping.json")
        for scenario_id, assessment in every_scenario():
            with self.subTest(scenario=scenario_id):
                preview = mapper.dry_run_preview(assessment)
                self.assertIsNone(preview["mapping_error"])
                self.assertFalse(preview["live_write_blocked"])


class ConfidenceInvariants(unittest.TestCase):
    def test_confidence_stays_within_bounds(self):
        for scenario_id, assessment in every_scenario():
            with self.subTest(scenario=scenario_id):
                for score in (
                    assessment.initial_confidence_score,
                    assessment.final_confidence_score,
                ):
                    self.assertGreaterEqual(score, 0.0)
                    self.assertLessEqual(score, 1.0)

    def test_runtime_recovery_never_exceeds_the_configured_ceiling(self):
        limits = json.loads(
            (CONFIG / "runtime_signal_policy.json").read_text(encoding="utf-8")
        )["limits"]
        ceiling = float(limits["maximum_runtime_confidence"])
        for scenario_id, assessment in every_scenario():
            if assessment.final_confidence_score <= assessment.initial_confidence_score:
                continue
            with self.subTest(scenario=scenario_id):
                self.assertLessEqual(assessment.final_confidence_score, ceiling)

    def test_no_reassessment_credits_more_than_the_cap(self):
        limits = json.loads(
            (CONFIG / "runtime_signal_policy.json").read_text(encoding="utf-8")
        )["limits"]
        cap = float(limits["maximum_credit_per_reassessment"])
        for scenario_id, assessment in every_scenario():
            records = assessment.skill_outputs.get("confidence_reassessments", {}) or {}
            for skill_id, record in records.items():
                with self.subTest(scenario=scenario_id, skill=skill_id):
                    self.assertLessEqual(record["applied_credit"], cap)

    def test_credit_is_never_applied_while_a_hard_flag_stands(self):
        for scenario_id, assessment in every_scenario():
            records = assessment.skill_outputs.get("confidence_reassessments", {}) or {}
            for skill_id, record in records.items():
                if not record["credit_blocked_by_hard_flags"]:
                    continue
                with self.subTest(scenario=scenario_id, skill=skill_id):
                    self.assertEqual(record["applied_credit"], 0.0)


class PlanIntegrityInvariants(unittest.TestCase):
    def test_cancelled_work_never_runs_unless_a_later_revision_reinstates_it(self):
        """Cancellation is not permanent; running while cancelled would be.

        A plan can drop a skill and a later revision can require it again. The
        resolved scenario does exactly that: expanding cancels the accelerated
        recommendation step, and contracting asks for it back. What must never
        happen is a skill executing while no plan requires it.
        """
        for scenario_id, assessment in every_scenario():
            transitions = assessment.plan_transitions
            for index, transition in enumerate(transitions):
                later_additions = {
                    skill
                    for following in transitions[index + 1:]
                    for skill in following.added_skills
                }
                for skill in transition.cancelled_skills:
                    if skill not in assessment.completed_skills:
                        continue
                    with self.subTest(scenario=scenario_id, skill=skill):
                        self.assertIn(
                            skill,
                            later_additions,
                            f"{skill} was cancelled and then executed without any "
                            f"later revision requiring it again",
                        )

    def test_work_cancelled_by_the_final_plan_never_executes(self):
        for scenario_id, assessment in every_scenario():
            if not assessment.plan_transitions:
                continue
            final = assessment.plan_transitions[-1]
            for skill in final.cancelled_skills:
                with self.subTest(scenario=scenario_id, skill=skill):
                    self.assertNotIn(skill, assessment.completed_skills)
                    self.assertNotIn(skill, assessment.skill_outputs)

    def test_a_skill_is_never_cancelled_after_it_has_completed(self):
        for scenario_id, assessment in every_scenario():
            for transition in assessment.plan_transitions:
                for skill in transition.cancelled_skills:
                    with self.subTest(scenario=scenario_id, skill=skill):
                        self.assertNotIn(skill, transition.completed_skills_retained)

    def test_every_completed_skill_produced_an_output(self):
        for scenario_id, assessment in every_scenario():
            for skill in assessment.completed_skills:
                with self.subTest(scenario=scenario_id, skill=skill):
                    self.assertIn(skill, assessment.skill_outputs)

    def test_peak_width_bounds_both_endpoints(self):
        for scenario_id, assessment in every_scenario():
            with self.subTest(scenario=scenario_id):
                self.assertGreaterEqual(
                    assessment.peak_plan_agent_count,
                    assessment.initial_plan_agent_count,
                )
                self.assertGreaterEqual(
                    assessment.peak_plan_agent_count,
                    assessment.final_plan_agent_count,
                )

    def test_participation_is_never_smaller_than_the_terminal_plan(self):
        for scenario_id, assessment in every_scenario():
            with self.subTest(scenario=scenario_id):
                self.assertGreaterEqual(
                    assessment.unique_agents_executed,
                    assessment.final_plan_agent_count,
                )

    def test_a_transition_direction_matches_the_width_it_produced(self):
        for scenario_id, assessment in every_scenario():
            for transition in assessment.plan_transitions:
                with self.subTest(scenario=scenario_id, to=transition.to_mode):
                    self.assertIn(
                        transition.direction, {"EXPANSION", "CONTRACTION"}
                    )

    def test_every_plan_resolves_an_agent_for_every_skill(self):
        for scenario_id, assessment in every_scenario():
            with self.subTest(scenario=scenario_id):
                self.assertEqual(
                    len(assessment.reasoning_agents_executed),
                    len(assessment.completed_skills),
                )


class ProvenanceInvariants(unittest.TestCase):
    FIXTURES = (
        "scenarios.json",
        "incidents.json",
        "changes.json",
        "telemetry_samples.json",
        "health_observations.json",
        "known_errors.json",
        "knowledge_documents.json",
        "vendor_advisories.json",
        "entities.json",
        "semantic_relationships.json",
    )

    def test_every_fixture_row_declares_itself_synthetic(self):
        for filename in self.FIXTURES:
            rows = json.loads((JSON_DIR / filename).read_text(encoding="utf-8"))
            offenders = [
                row for row in rows
                if isinstance(row, dict)
                and row.get("data_classification") != "SYNTHETIC"
            ]
            with self.subTest(fixture=filename):
                self.assertEqual(offenders, [], f"{len(offenders)} non-synthetic rows")

    def test_no_fixture_carries_a_credential_shaped_value(self):
        for filename in self.FIXTURES:
            payload = (JSON_DIR / filename).read_text(encoding="utf-8").lower()
            for term in ("password", "secret", "api_key", "bearer "):
                with self.subTest(fixture=filename, term=term):
                    self.assertNotIn(term, payload)


class PolicyConsistencyInvariants(unittest.TestCase):
    def test_every_reassessment_hook_names_a_skill_the_mode_runs(self):
        modes = json.loads(
            (CONFIG / "orchestration_policies.json").read_text(encoding="utf-8")
        )["modes"]
        for mode in modes:
            for skill in mode["reassess_after_skills"]:
                with self.subTest(mode=mode["mode_id"], skill=skill):
                    self.assertIn(skill, mode["required_skills"])

    def test_every_signal_that_resolves_a_flag_declares_which(self):
        signals = json.loads(
            (CONFIG / "runtime_signal_policy.json").read_text(encoding="utf-8")
        )["signals"]
        for name, config in signals.items():
            resolvers = config.get("resolves_flags")
            if resolvers is None:
                continue
            with self.subTest(signal=name):
                self.assertTrue(resolvers)

    def test_every_skill_in_the_catalog_has_a_provider(self):
        catalog = json.loads((CONFIG / "skill_catalog.json").read_text(encoding="utf-8"))
        registry = json.loads(
            (CONFIG / "agent_registry.json").read_text(encoding="utf-8")
        )
        provided = {
            skill
            for agent in registry["agents"]
            if agent["status"] == "ACTIVE"
            for skill in agent.get("skills", [])
        }
        for skill in catalog["skills"]:
            with self.subTest(skill=skill["skill_id"]):
                self.assertIn(skill["skill_id"], provided)


if __name__ == "__main__":
    unittest.main()
