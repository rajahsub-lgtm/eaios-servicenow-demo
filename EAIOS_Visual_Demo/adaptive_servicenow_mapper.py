from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import json

from adaptive_execution_orchestrator import AdaptiveExecutionAssessment


class ServiceNowMappingError(ValueError):
    pass


class AdaptiveServiceNowMapper:
    def __init__(self, mapping_file: str | Path) -> None:
        self.mapping_file = Path(mapping_file)
        self.mapping = json.loads(
            self.mapping_file.read_text(encoding="utf-8")
        )

    @property
    def target_table(self) -> str:
        return self.mapping["target_table"]

    @property
    def correlation_field(self) -> str:
        concept = self.mapping["correlation_concept"]
        rule = self.mapping["fields"][concept]
        name = rule.get("internal_name")

        if not name or not rule.get("confirmed"):
            raise ServiceNowMappingError(
                "Correlation ID field is not confirmed in the mapping."
            )

        return name

    def conceptual_values(
        self,
        assessment: AdaptiveExecutionAssessment,
    ) -> dict[str, Any]:
        recommendation = assessment.recommendation
        context = assessment.skill_outputs.get("semantic_context", {})
        knowledge = assessment.skill_outputs.get(
            "governed_knowledge_retrieval",
            {},
        )

        limited = knowledge.get("accepted_with_limitations", [])
        evidence_summary = {
            "completed_skills": assessment.completed_skills,
            "reasoning_agents_executed": (
                assessment.reasoning_agents_executed
            ),
            "initial_agent_count": assessment.initial_agent_count,
            "final_agent_count": assessment.final_agent_count,
            "policy_decision_counts": assessment.policy_decision_counts,
            "accepted_free_text_ids": [
                row.get("source_id")
                for row in knowledge.get("accepted_free_text", [])
            ],
            "accepted_with_limitations_ids": [
                row.get("source_id") for row in limited
            ],
            "material_conflicts": [
                {
                    "source_id": row.get("source_id"),
                    "conflicts_with": row.get(
                        "contradicts_known_error_ids",
                        [],
                    ),
                    "alternative_hypothesis_id": row.get(
                        "alternative_hypothesis_id"
                    ),
                    "corroboration_count": row.get(
                        "corroboration_count",
                        0,
                    ),
                    "disposition": row.get("governance_decision"),
                    "reasons": row.get("limitation_reasons", []),
                }
                for row in limited
                if row.get("material_contradiction")
            ],
            "accepted_structured_record_ids": [
                row.get("source_id")
                for row in knowledge.get(
                    "accepted_structured_records",
                    [],
                )
            ],
            "rejected_evidence_ids": [
                row.get("source_id")
                for row in knowledge.get("rejected_candidates", [])
            ],
            "plan_transitions": [
                asdict(row) for row in assessment.plan_transitions
            ],
            "confidence": {
                "initial_score": assessment.initial_confidence_score,
                "final_score": assessment.final_confidence_score,
                "initial_level": assessment.initial_confidence_level,
                "final_level": assessment.final_confidence_level,
                "drift_status": assessment.drift_status,
            },
            "automation_readiness": assessment.automation_readiness,
        }

        business_impact = {
            "impacted_capability_ids": context.get(
                "impacted_capability_ids",
                [],
            ),
            "business_outcome_ids": context.get(
                "business_outcome_ids",
                [],
            ),
            "authoritative_entity_ids": context.get(
                "authoritative_entity_ids",
                [],
            ),
        }

        return {
            "Correlation ID": assessment.correlation_id,
            "External observation ID": context.get(
                "trigger_observation_id",
                "",
            ),
            "Scenario ID": assessment.scenario_id,
            "Primary service ID": context.get("primary_service_id", ""),
            "Primary component ID": context.get(
                "primary_component_id",
                "",
            ),
            "Business impact": json.dumps(
                business_impact,
                separators=(",", ":"),
            ),
            "Leading hypothesis": (
                f"{recommendation['leading_hypothesis_id']}: "
                f"{recommendation['leading_hypothesis_title']}"
            ),
            "Alternative hypotheses": ",".join(
                recommendation.get("alternative_hypothesis_ids", [])
            ),
            "Selected strategy": recommendation["selected_strategy"],
            "Confidence": assessment.final_confidence_level,
            "Confidence score": assessment.final_confidence_score,
            "Initial confidence score": assessment.initial_confidence_score,
            "Final confidence score": assessment.final_confidence_score,
            "Confidence trend": (
                "ERODING"
                if assessment.drift_status == "ERODING"
                else "STABLE"
            ),
            "Drift status": assessment.drift_status,
            "Initial plan mode": assessment.initial_plan_mode,
            "Final plan mode": assessment.final_plan_mode,
            "Expanded during execution": (
                assessment.expanded_during_execution
            ),
            "Initial agent count": assessment.initial_agent_count,
            "Final agent count": assessment.final_agent_count,
            "Plan revision reason": (
                assessment.plan_transitions[-1].reason
                if assessment.plan_transitions
                else "No plan revision required"
            ),
            "Automation readiness": assessment.automation_readiness.get(
                "status",
                "UNKNOWN",
            ),
            "Automation readiness rationale": assessment.automation_readiness.get(
                "explanation",
                "",
            ),
            "Safety status": assessment.safety_status,
            "Approval required": recommendation.get(
                "human_approval_required",
                True,
            ),
            "Approval state": assessment.approval_state,
            "Recommended action": recommendation["recommended_action"],
            "Validation steps": "\n".join(
                recommendation.get("validation_steps", [])
            ),
            "Evidence summary": json.dumps(
                evidence_summary,
                separators=(",", ":"),
            ),
            "Uncertainty factors": ",".join(
                recommendation.get("uncertainty_factors", [])
            ),
            "Guardrail reasons": ",".join(
                recommendation.get("guardrail_reasons", [])
            ),
            "Reasoning summary": recommendation.get(
                "reasoning_summary",
                "",
            ),
            "Execution trace": json.dumps(
                [asdict(row) for row in assessment.execution_trace],
                separators=(",", ":"),
            ),
            "Policy decision summary": json.dumps(
                {
                    "counts": assessment.policy_decision_counts,
                    "decision_ids": [
                        row.decision_id
                        for row in assessment.policy_decisions
                    ],
                },
                separators=(",", ":"),
            ),
            "EAIOS response timestamp": assessment.generated_at,
            "Outcome": "Pending",
        }

    def validate_live_mapping(self) -> None:
        missing = []

        for concept, rule in self.mapping["fields"].items():
            if rule.get("required") and (
                not rule.get("internal_name")
                or not rule.get("confirmed")
            ):
                missing.append(concept)

        if missing:
            raise ServiceNowMappingError(
                "Required ServiceNow fields are not confirmed: "
                + ", ".join(missing)
            )

    def map_for_live(
        self,
        assessment: AdaptiveExecutionAssessment,
    ) -> dict[str, Any]:
        self.validate_live_mapping()

        conceptual = self.conceptual_values(assessment)
        payload: dict[str, Any] = {}

        for concept, value in conceptual.items():
            rule = self.mapping["fields"].get(concept)

            if not rule or not rule.get("confirmed"):
                continue

            internal_name = rule.get("internal_name")
            if not internal_name:
                continue

            value_mapping = rule.get("value_mapping", {})
            mapped_value = value_mapping.get(str(value), value)

            payload[internal_name] = mapped_value

        return payload

    def dry_run_preview(
        self,
        assessment: AdaptiveExecutionAssessment,
    ) -> dict[str, Any]:
        conceptual = self.conceptual_values(assessment)

        try:
            mapped_payload = self.map_for_live(assessment)
            mapping_error = None
            live_write_blocked = False
        except ServiceNowMappingError as exc:
            mapped_payload = {}
            mapping_error = str(exc)
            live_write_blocked = True

        return {
            "mode": "DRY_RUN",
            "target_table": self.target_table,
            "mapping_status": self.mapping.get("status", "UNKNOWN"),
            "conceptual_values": conceptual,
            "mapped_servicenow_payload": mapped_payload,
            "mapping_error": mapping_error,
            "live_write_blocked": live_write_blocked,
        }
