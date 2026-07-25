from pathlib import Path
import unittest

from telemetry_agent import TelemetryAnalysisAgent


ROOT = Path(__file__).resolve().parent


class TelemetryAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = TelemetryAnalysisAgent(ROOT / "json")

    def test_payment_analysis_uses_no_future_samples(self):
        result = self.agent.analyze("SCN-PAY-001")
        self.assertEqual(result.trigger_observation_id, "OBS-PAY-006")
        self.assertGreater(result.future_samples_excluded, 0)
        self.assertEqual(result.analysis_window_end, "2026-07-14 14:50:00")

    def test_payment_trigger_metric_reaches_expected_value(self):
        result = self.agent.analyze("SCN-PAY-001")
        trigger = result.trigger_metric_summary
        self.assertEqual(trigger.metric_id, "MET-PAY-TIMEOUT")
        self.assertEqual(trigger.entity_id, "COMP-PAY-CONNECTOR")
        self.assertEqual(trigger.latest_value, 18.7)
        self.assertEqual(trigger.current_status, "CRITICAL")

    def test_payment_database_pressure_is_earliest_warning(self):
        result = self.agent.analyze("SCN-PAY-001")
        first = result.timeline[0]
        self.assertEqual(first.metric_id, "MET-DB-UTIL")
        self.assertEqual(first.observed_at, "2026-07-14 14:25:00")

    def test_queue_analysis_detects_cross_service_degradation(self):
        result = self.agent.analyze("SCN-QUEUE-001")
        critical_metrics = {
            summary.metric_id
            for summary in result.metric_summaries
            if summary.current_status == "CRITICAL"
        }
        self.assertTrue(
            {
                "MET-QUEUE-DEPTH",
                "MET-CONSUMER-LAG",
                "MET-ACC-DELAY",
                "MET-FRAUD-DELAY",
                "MET-ALERT-COUNT",
            }.issubset(critical_metrics)
        )

    def test_temporal_explanation_does_not_claim_causation(self):
        result = self.agent.analyze("SCN-QUEUE-001")
        self.assertIn("not causation", result.temporal_explanation)


if __name__ == "__main__":
    unittest.main()
