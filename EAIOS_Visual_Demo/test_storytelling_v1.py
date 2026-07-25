from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from automation_readiness import AutomationReadinessEvaluator
from operational_confidence_engine import OperationalConfidenceEngine


ROOT = Path(__file__).resolve().parent


class StorytellingV1Tests(unittest.TestCase):
    def test_contradictory_knowledge_erodes_confidence_and_expands_plan(self):
        result = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id="TEST-CONTRADICTORY-KNOWLEDGE",
            scenario_id="SCN-PAY-CONTRADICT-001",
        )

        self.assertEqual(result.initial_confidence_level, "HIGH")
        self.assertEqual(result.final_confidence_level, "MEDIUM")
        self.assertGreater(result.initial_confidence_score, result.final_confidence_score)
        self.assertEqual(result.initial_plan_mode, "ACCELERATED_VALIDATION")
        self.assertEqual(result.final_plan_mode, "FULL_INVESTIGATION")
        self.assertTrue(result.expanded_during_execution)
        self.assertEqual(result.initial_agent_count, 3)
        self.assertEqual(result.final_agent_count, 6)
        self.assertEqual(len(result.plan_transitions), 1)

        retrieval = result.skill_outputs["governed_knowledge_retrieval"]
        limited = {
            row["source_id"]: row
            for row in retrieval["accepted_with_limitations"]
        }
        article = limited["KB-CONTRADICT-001"]
        self.assertEqual(
            article["governance_decision"],
            "ACCEPTED_WITH_LIMITATIONS",
        )
        self.assertTrue(article["material_contradiction"])
        self.assertIn("MATERIAL_CONTRADICTION", article["limitation_reasons"])
        self.assertIn(
            "NO_INDEPENDENT_CORROBORATION",
            article["limitation_reasons"],
        )
        self.assertTrue(result.recommendation["unresolved_material_conflict"])
        self.assertIn(
            "KB-CONTRADICT-001",
            result.recommendation["material_conflict_source_ids"],
        )

    def test_runtime_contradiction_is_scoped_to_the_new_scenario(self):
        result = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id="TEST-STABLE-SCOPE",
            scenario_id="SCN-PAY-001",
        )
        self.assertEqual(result.initial_plan_mode, "ACCELERATED_VALIDATION")
        self.assertEqual(result.final_plan_mode, "ACCELERATED_VALIDATION")
        self.assertFalse(result.expanded_during_execution)
        self.assertEqual(result.reasoning_agent_execution_count, 3)

    def test_mature_stable_pattern_is_candidate_but_hitl_remains(self):
        orchestrator = AdaptiveExecutionOrchestrator(ROOT)
        result = orchestrator.execute(
            correlation_id="TEST-READINESS-CANDIDATE",
            scenario_id="SCN-PAY-001",
        )
        readiness = result.automation_readiness
        self.assertEqual(readiness["status"], "CANDIDATE")
        self.assertTrue(readiness["advisory_only"])
        self.assertTrue(readiness["human_approval_enforced"])
        self.assertEqual(result.approval_state, "AWAITING_APPROVAL")

    def test_contradiction_suspends_automation_readiness(self):
        result = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id="TEST-READINESS-SUSPENDED",
            scenario_id="SCN-PAY-CONTRADICT-001",
        )
        self.assertEqual(result.automation_readiness["status"], "SUSPENDED")
        self.assertIn(
            "CREDIBLE_KNOWLEDGE_CONTRADICTION",
            result.automation_readiness["blockers"],
        )
        self.assertTrue(result.automation_readiness["human_approval_enforced"])

    def test_successful_outcome_volume_matures_confidence(self):
        rows = json.loads(
            (ROOT / "json" / "outcome_history.json").read_text(encoding="utf-8")
        )
        payment = sorted(
            [row for row in rows if row["known_error_id"] == "KE-PAY-001"],
            key=lambda row: row["recorded_at"],
        )
        others = [row for row in rows if row["known_error_id"] != "KE-PAY-001"]

        scores = []
        levels = []
        maturities = []
        for sample_size in (1, 5, 10, 15):
            with TemporaryDirectory() as directory:
                json_copy = Path(directory) / "json"
                shutil.copytree(ROOT / "json", json_copy)
                (json_copy / "outcome_history.json").write_text(
                    json.dumps(others + payment[:sample_size], indent=2),
                    encoding="utf-8",
                )
                engine = OperationalConfidenceEngine(
                    json_copy,
                    ROOT / "config" / "confidence_policy.json",
                )
                assessment = engine.assess("SCN-PAY-001")
                profile = assessment.candidate_assessments[0].outcome_profile
                scores.append(assessment.confidence_score)
                levels.append(assessment.confidence_level)
                maturities.append(profile.sample_maturity)

        self.assertEqual(scores, sorted(scores))
        self.assertEqual(maturities, sorted(maturities))
        self.assertEqual(levels[0], "MEDIUM")
        self.assertEqual(levels[-1], "HIGH")


if __name__ == "__main__":
    unittest.main()
