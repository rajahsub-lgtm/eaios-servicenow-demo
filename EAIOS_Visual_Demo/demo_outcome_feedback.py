from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from demo_adaptive_planning import build_planner
from outcome_feedback import OutcomeFeedbackStore, OutcomeInput, feedback_from_assessment


ROOT = Path(__file__).resolve().parent


def main() -> None:
    baseline = build_planner().plan("SCN-PAY-001")
    print("=== BEFORE SERVICENOW OUTCOME FEEDBACK ===")
    print(f"{baseline.orchestration_mode} | {baseline.confidence_level} {baseline.confidence_score:.3f}")

    with TemporaryDirectory() as directory:
        json_copy = Path(directory) / "json"
        shutil.copytree(ROOT / "json", json_copy)
        assessment = AdaptiveExecutionOrchestrator(ROOT, json_dir=json_copy).execute(
            correlation_id="EAIOS-FEEDBACK-PAY-001",
            scenario_id="SCN-PAY-001",
        )
        store = OutcomeFeedbackStore(json_copy / "runtime_outcome_feedback.json")

        for index in range(8):
            outcome = OutcomeInput(
                approval_decision="Approved",
                human_modification="Expanded investigation requested",
                action_performed="Connector validation and restart",
                outcome="Failed",
                recovery_minutes=80 + index,
                recurrence_within_24h=True,
                evidence_usefulness_score=35,
                recorded_at=f"2026-07-{16 + index:02d} 15:00:00",
            )
            feedback = feedback_from_assessment(
                assessment,
                outcome,
                outcome_id=f"OUT-SNOW-FEEDBACK-{index+1:03d}",
            )
            store.append(feedback)

        changed = build_planner(json_copy).plan(
            "SCN-PAY-001", as_of="2026-07-24 16:00:00"
        )
        print("=== AFTER RECENT FAILED/RECURRING OUTCOMES ===")
        print(f"{changed.orchestration_mode} | {changed.confidence_level} {changed.confidence_score:.3f}")
        print(f"Drift: {changed.drift_status}")
        print("ServiceNow-style outcome feedback changed future orchestration without code changes.")


if __name__ == "__main__":
    main()
