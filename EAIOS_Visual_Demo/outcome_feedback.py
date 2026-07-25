from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import uuid

from adaptive_execution_orchestrator import AdaptiveExecutionAssessment


@dataclass(frozen=True)
class OutcomeInput:
    approval_decision: str
    human_modification: str
    action_performed: str
    outcome: str
    recovery_minutes: float
    recurrence_within_24h: bool
    evidence_usefulness_score: float
    recorded_at: str


@dataclass(frozen=True)
class OutcomeFeedback:
    outcome_id: str
    correlation_id: str
    known_error_id: str
    scenario_pattern: str
    entity_id: str
    recommendation: str
    approval_decision: str
    human_modification: str
    action_performed: str
    outcome: str
    recovery_minutes: float
    recurrence_within_24h: bool
    prior_confidence: str
    evidence_usefulness_score: float
    recorded_at: str
    data_classification: str


class OutcomeFeedbackStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def list(self) -> list[dict[str, Any]]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def append(self, feedback: OutcomeFeedback) -> bool:
        rows = self.list()
        if any(row.get("outcome_id") == feedback.outcome_id for row in rows):
            return False
        rows.append(asdict(feedback))
        self.path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        return True


def feedback_from_assessment(
    assessment: AdaptiveExecutionAssessment,
    outcome: OutcomeInput,
    *,
    outcome_id: str | None = None,
) -> OutcomeFeedback:
    recommendation = assessment.recommendation
    context = assessment.skill_outputs["semantic_context"]
    return OutcomeFeedback(
        outcome_id=outcome_id or f"OUT-FEEDBACK-{uuid.uuid4().hex[:12].upper()}",
        correlation_id=assessment.correlation_id,
        known_error_id=recommendation["leading_hypothesis_id"],
        scenario_pattern=recommendation["leading_hypothesis_id"],
        entity_id=context["primary_component_id"],
        recommendation=recommendation["recommended_action"],
        approval_decision=outcome.approval_decision,
        human_modification=outcome.human_modification,
        action_performed=outcome.action_performed,
        outcome=outcome.outcome,
        recovery_minutes=float(outcome.recovery_minutes),
        recurrence_within_24h=bool(outcome.recurrence_within_24h),
        prior_confidence=assessment.final_confidence_level,
        evidence_usefulness_score=float(outcome.evidence_usefulness_score),
        recorded_at=outcome.recorded_at,
        data_classification="SYNTHETIC",
    )
