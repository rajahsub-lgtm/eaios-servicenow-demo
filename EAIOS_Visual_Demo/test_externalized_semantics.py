"""Meaning belongs in data, not in the code that consumes it.

Two values were embedded in Python: the symptom vocabulary for each metric,
and the confidence bar drawn on the charts. Both describe the domain rather
than the mechanism, and both had a second source of truth in JSON that could
silently disagree with them.
"""

from pathlib import Path
import json
import unittest

from eaios_story_data import StoryRepository
from knowledge_retrieval_agent import METRIC_SYMPTOMS, KnowledgeRetrievalAgent


ROOT = Path(__file__).resolve().parent
JSON_DIR = ROOT / "json"
CONFIG = ROOT / "config"


def agent() -> KnowledgeRetrievalAgent:
    return KnowledgeRetrievalAgent(JSON_DIR)


def metric_definitions() -> list[dict]:
    return json.loads((JSON_DIR / "metric_definitions.json").read_text(encoding="utf-8"))


class MetricSymptomSourceTests(unittest.TestCase):
    def test_definitions_declare_their_own_symptoms(self):
        declared = [row for row in metric_definitions() if row.get("symptom_categories")]
        self.assertGreaterEqual(len(declared), 13)

    def test_declared_symptoms_take_precedence_over_the_fallback(self):
        subject = agent()
        subject.metric_symptoms["MET-PAY-TIMEOUT"] = {"DECLARED_WINS"}
        self.assertEqual(subject._symptoms_for("MET-PAY-TIMEOUT"), {"DECLARED_WINS"})
        self.assertEqual(METRIC_SYMPTOMS["MET-PAY-TIMEOUT"], {"PAYMENT_TIMEOUT"})

    def test_the_fallback_still_answers_for_undeclared_metrics(self):
        subject = agent()
        subject.metric_symptoms = {}
        self.assertEqual(subject._symptoms_for("MET-PAY-TIMEOUT"), {"PAYMENT_TIMEOUT"})

    def test_an_unknown_metric_resolves_to_nothing_rather_than_failing(self):
        self.assertEqual(agent()._symptoms_for("MET-DOES-NOT-EXIST"), set())

    def test_declared_values_agree_with_the_fallback_they_replace(self):
        """Externalising meaning must not quietly change it."""
        subject = agent()
        for metric_id, legacy in METRIC_SYMPTOMS.items():
            declared = subject.metric_symptoms.get(metric_id)
            if declared is None:
                continue
            with self.subTest(metric=metric_id):
                self.assertEqual(declared, legacy)

    def test_v1_symptom_derivation_is_unchanged(self):
        retrieval = agent().retrieve("SCN-PAY-001")
        self.assertIn("PAYMENT_TIMEOUT", retrieval.symptom_categories)


class ReadinessThresholdSourceTests(unittest.TestCase):
    def test_the_threshold_comes_from_readiness_policy(self):
        policy = json.loads(
            (CONFIG / "automation_readiness_policy.json").read_text(encoding="utf-8")
        )
        expected = float(policy["thresholds"]["minimum_confidence_score"])
        self.assertEqual(
            StoryRepository.load(ROOT).readiness_confidence_threshold(), expected
        )

    def test_the_charts_hold_no_literal_threshold(self):
        source = (ROOT / "eaios_story_app.py").read_text(encoding="utf-8")
        self.assertNotIn("add_hline(y=0.9", source)
        self.assertIn("readiness_confidence_threshold()", source)

    def test_the_chart_and_the_evaluator_cannot_disagree(self):
        """Whatever the policy says is what the chart draws."""
        repo = StoryRepository.load(ROOT)
        policy = json.loads(
            (CONFIG / "automation_readiness_policy.json").read_text(encoding="utf-8")
        )
        chart_value = repo.readiness_confidence_threshold()
        evaluator_value = float(policy["thresholds"]["minimum_confidence_score"])
        self.assertEqual(chart_value, evaluator_value)

    def test_a_missing_policy_falls_back_rather_than_crashing(self):
        from dataclasses import replace as dataclass_replace

        repo = StoryRepository.load(ROOT)
        detached = dataclass_replace(
            repo, paths=dataclass_replace(repo.paths, base_dir=Path("/nonexistent"))
        )
        self.assertEqual(detached.readiness_confidence_threshold(), 0.9)


if __name__ == "__main__":
    unittest.main()
