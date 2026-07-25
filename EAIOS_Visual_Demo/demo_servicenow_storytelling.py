from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import json
import shutil

from adaptive_execution_orchestrator import AdaptiveExecutionAssessment, AdaptiveExecutionOrchestrator
from adaptive_servicenow_mapper import AdaptiveServiceNowMapper
from automation_readiness import AutomationReadinessEvaluator
from operational_confidence_engine import OperationalConfidenceEngine


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def maturity_checkpoints() -> list[dict]:
    outcome_rows = json.loads(
        (ROOT / "json" / "outcome_history.json").read_text(encoding="utf-8")
    )
    payment = sorted(
        [row for row in outcome_rows if row["known_error_id"] == "KE-PAY-001"],
        key=lambda row: row["recorded_at"],
    )
    other = [row for row in outcome_rows if row["known_error_id"] != "KE-PAY-001"]
    evaluator = AutomationReadinessEvaluator(
        ROOT / "config" / "automation_readiness_policy.json"
    )

    checkpoints = []
    for sample_size in (1, 5, 10, 15, 25, 40, 50):
        with TemporaryDirectory() as directory:
            json_copy = Path(directory) / "json"
            shutil.copytree(ROOT / "json", json_copy)
            (json_copy / "outcome_history.json").write_text(
                json.dumps(other + payment[:sample_size], indent=2),
                encoding="utf-8",
            )
            engine = OperationalConfidenceEngine(
                json_copy,
                ROOT / "config" / "confidence_policy.json",
            )
            assessment = engine.assess("SCN-PAY-001")
            profile = assessment.candidate_assessments[0].outcome_profile
            readiness = evaluator.evaluate(assessment)
            checkpoints.append(
                {
                    "checkpoint": f"{sample_size} outcomes",
                    "sample_size": sample_size,
                    "sample_maturity": profile.sample_maturity,
                    "confidence_score": assessment.confidence_score,
                    "confidence_level": assessment.confidence_level,
                    "recent_success_rate": profile.recent_success_rate,
                    "recent_recurrence_rate": profile.recent_recurrence_rate,
                    "drift_status": assessment.drift_status,
                    "automation_readiness": readiness.status,
                    "human_approval_enforced": readiness.human_approval_enforced,
                }
            )
    return checkpoints


def execution_event_rows(
    assessment: AdaptiveExecutionAssessment,
) -> list[dict]:
    rows: list[dict] = []
    rows.append(
        {
            "correlation_id": assessment.correlation_id,
            "assessment_scenario": assessment.scenario_name,
            "sequence": 0,
            "event_type": "INITIAL_PLAN_SELECTED",
            "skill_id": "",
            "agent_id": "",
            "agent_name": "",
            "status": "SUCCEEDED",
            "confidence_before": "",
            "confidence_after": assessment.initial_confidence_score,
            "confidence_level_before": "",
            "confidence_level_after": assessment.initial_confidence_level,
            "plan_before": "",
            "plan_after": assessment.initial_plan_mode,
            "agent_count_before": "",
            "agent_count_after": assessment.initial_agent_count,
            "summary": (
                f"Initial {assessment.initial_plan_mode} plan selected from "
                f"{assessment.initial_confidence_level} confidence."
            ),
        }
    )

    reassessments = assessment.skill_outputs.get(
        "confidence_reassessments"
    ) or {}
    if not reassessments:
        legacy = assessment.skill_outputs.get("confidence_reassessment")
        if legacy:
            reassessments = {"due_diligence_validation": legacy}
    transition_by_skill = {
        transition.triggered_after_skill: transition
        for transition in assessment.plan_transitions
    }

    for trace in assessment.execution_trace:
        event_type = "SKILL_COMPLETED"
        confidence_before = ""
        confidence_after = ""
        confidence_level_before = ""
        confidence_level_after = ""
        plan_before = ""
        plan_after = ""
        agent_count_before = ""
        agent_count_after = ""
        summary = trace.summary

        reassessment = reassessments.get(trace.skill_id)
        if reassessment:
            before = reassessment.get("initial_confidence_score", 0)
            after = reassessment.get("updated_confidence_score", 0)
            if after < before:
                event_type = "CONFIDENCE_ERODED"
            elif after > before:
                event_type = "CONFIDENCE_RESTORED"
            else:
                event_type = "CONFIDENCE_RECONFIRMED"
            confidence_before = before
            confidence_after = after
            confidence_level_before = reassessment.get("initial_confidence_level", "")
            confidence_level_after = reassessment.get("updated_confidence_level", "")

            transition = transition_by_skill.get(trace.skill_id)
            if transition:
                plan_before = transition.from_mode
                plan_after = transition.to_mode
            else:
                plan_before = assessment.initial_plan_mode
                plan_after = assessment.final_plan_mode
            agent_count_before = assessment.initial_agent_count
            agent_count_after = assessment.final_agent_count
            signal_types = reassessment.get("runtime_signal_types", [])
            summary = (
                f"{trace.summary} Runtime evidence {signal_types} changed "
                f"confidence and caused the planner to reassess required skills."
            )

        rows.append(
            {
                "correlation_id": assessment.correlation_id,
                "assessment_scenario": assessment.scenario_name,
                "sequence": trace.sequence,
                "event_type": event_type,
                "skill_id": trace.skill_id,
                "agent_id": trace.agent_id,
                "agent_name": trace.agent_name,
                "status": trace.status,
                "confidence_before": confidence_before,
                "confidence_after": confidence_after,
                "confidence_level_before": confidence_level_before,
                "confidence_level_after": confidence_level_after,
                "plan_before": plan_before,
                "plan_after": plan_after,
                "agent_count_before": agent_count_before,
                "agent_count_after": agent_count_after,
                "summary": summary,
            }
        )
    return rows


def plan_revision_rows(
    assessment: AdaptiveExecutionAssessment,
) -> list[dict]:
    rows = []
    for index, transition in enumerate(assessment.plan_transitions, start=1):
        rows.append(
            {
                "correlation_id": assessment.correlation_id,
                "revision_number": index,
                "previous_plan_mode": transition.from_mode,
                "new_plan_mode": transition.to_mode,
                "confidence_before": assessment.initial_confidence_score,
                "confidence_after": assessment.final_confidence_score,
                "confidence_level_before": assessment.initial_confidence_level,
                "confidence_level_after": assessment.final_confidence_level,
                "agent_count_before": assessment.initial_agent_count,
                "agent_count_after": assessment.final_agent_count,
                "direction": transition.direction,
                "expanded": transition.direction == "EXPANSION",
                "triggered_after_skill": transition.triggered_after_skill,
                "preserved_completed_skills": ",".join(
                    transition.completed_skills_retained
                ),
                "added_skills": ",".join(transition.added_skills),
                "cancelled_skills": ",".join(transition.cancelled_skills),
                "revision_reason": transition.reason,
            }
        )
    return rows


def readiness_row(assessment: AdaptiveExecutionAssessment) -> dict:
    readiness = assessment.automation_readiness
    return {
        "correlation_id": assessment.correlation_id,
        "scenario": assessment.scenario_name,
        "confidence_score": assessment.final_confidence_score,
        "confidence_level": assessment.final_confidence_level,
        "drift_status": assessment.drift_status,
        "automation_readiness": readiness["status"],
        "human_approval_enforced": readiness["human_approval_enforced"],
        "blockers": ",".join(readiness["blockers"]),
        "required_constraints": ",".join(readiness["required_constraints"]),
        "explanation": readiness["explanation"],
    }


def plan_summary_row(assessment: AdaptiveExecutionAssessment) -> dict:
    """Canonical plan metrics, kept out of the frozen V1 CSV schemas.

    Plan width and agent participation are separate measurements. Width comes
    from resolved plans; participation comes from the execution trace. A
    contraction ends narrower than it peaked while still having drawn on every
    agent that contributed, so neither number can be derived from the other.
    """
    path = [assessment.initial_plan_mode] + [
        transition.to_mode for transition in assessment.plan_transitions
    ]
    return {
        "correlation_id": assessment.correlation_id,
        "scenario": assessment.scenario_name,
        "plan_path": " -> ".join(path),
        "initial_plan_agent_count": assessment.initial_plan_agent_count,
        "peak_plan_agent_count": assessment.peak_plan_agent_count,
        "final_plan_agent_count": assessment.final_plan_agent_count,
        "unique_agents_executed": assessment.unique_agents_executed,
        "expanded_during_execution": assessment.expanded_during_execution,
        "contracted_during_execution": assessment.contracted_during_execution,
        "revision_count": len(assessment.plan_transitions),
    }


def main() -> None:
    OUTPUTS.mkdir(exist_ok=True)
    orchestrator = AdaptiveExecutionOrchestrator(ROOT)
    mapper = AdaptiveServiceNowMapper(
        ROOT / "config" / "servicenow_field_mapping.json"
    )

    stable = orchestrator.execute(
        correlation_id="EAIOS-DEMO-STABLE-001",
        scenario_id="SCN-PAY-001",
    )
    contradiction = orchestrator.execute(
        correlation_id="EAIOS-DEMO-CONTRADICTION-001",
        scenario_id="SCN-PAY-CONTRADICT-001",
    )
    resolved = orchestrator.execute(
        correlation_id="EAIOS-DEMO-RESOLVED-001",
        scenario_id="SCN-PAY-RESOLVED-001",
    )
    assessments = [stable, contradiction, resolved]

    bundle = {
        "demo_version": "V1 ServiceNow Storytelling",
        "architecture_scope": (
            "Existing adaptive EAIOS behavior projected into ServiceNow. "
            "Human approval remains enforced."
        ),
        "assessments": [asdict(item) for item in assessments],
        "servicenow_previews": [
            mapper.dry_run_preview(item) for item in assessments
        ],
        "confidence_maturation": maturity_checkpoints(),
    }
    (OUTPUTS / "servicenow_story_bundle.json").write_text(
        json.dumps(bundle, indent=2),
        encoding="utf-8",
    )

    execution_rows = []
    revision_rows = []
    readiness_rows = []
    plan_summary_rows = []
    for assessment in assessments:
        execution_rows.extend(execution_event_rows(assessment))
        revision_rows.extend(plan_revision_rows(assessment))
        readiness_rows.append(readiness_row(assessment))
        plan_summary_rows.append(plan_summary_row(assessment))

    write_csv(OUTPUTS / "servicenow_execution_events.csv", execution_rows)
    write_csv(OUTPUTS / "servicenow_plan_revisions.csv", revision_rows)
    write_csv(OUTPUTS / "servicenow_automation_readiness.csv", readiness_rows)
    write_csv(OUTPUTS / "servicenow_plan_summary.csv", plan_summary_rows)
    write_csv(OUTPUTS / "servicenow_confidence_maturation.csv", maturity_checkpoints())

    print("=== EAIOS SERVICENOW STORYTELLING V1 ===")
    for assessment in assessments:
        print()
        print(assessment.scenario_name)
        print(
            f"Confidence: {assessment.initial_confidence_level} "
            f"{assessment.initial_confidence_score:.3f} -> "
            f"{assessment.final_confidence_level} "
            f"{assessment.final_confidence_score:.3f}"
        )
        print(
            f"Plan: {assessment.initial_plan_mode} -> "
            f"{assessment.final_plan_mode}"
        )
        print(
            f"Agents involved: {assessment.initial_agent_count} -> "
            f"{assessment.final_agent_count}"
        )
        print(
            f"Automation readiness: "
            f"{assessment.automation_readiness['status']} "
            f"(HITL enforced: "
            f"{assessment.automation_readiness['human_approval_enforced']})"
        )
        if assessment.recommendation.get("material_conflict_source_ids"):
            print(
                "Material knowledge conflict: "
                + ", ".join(
                    assessment.recommendation["material_conflict_source_ids"]
                )
            )
    print()
    print(f"Saved ServiceNow story artifacts under: {OUTPUTS}")


if __name__ == "__main__":
    main()
