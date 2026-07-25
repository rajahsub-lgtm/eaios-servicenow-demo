from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

from operational_confidence_engine import OperationalConfidenceAssessment


@dataclass(frozen=True)
class ReadinessCriterion:
    criterion_id: str
    label: str
    passed: bool
    actual: Any
    required: Any
    explanation: str


@dataclass(frozen=True)
class AutomationReadinessAssessment:
    status: str
    advisory_only: bool
    human_approval_enforced: bool
    selected_known_error_id: str | None
    confidence_score: float
    confidence_level: str
    criteria: list[ReadinessCriterion]
    blockers: list[str]
    required_constraints: list[str]
    explanation: str


class AutomationReadinessEvaluator:
    """Advisory maturity signal; never removes HITL in V1.

    Confidence is necessary but insufficient. Outcome sample size, recent
    success, recurrence, drift, contradiction, action controls, and policy all
    contribute to readiness. The result is a storytelling and governance signal,
    not an execution authorization.
    """

    def __init__(self, policy_file: str | Path) -> None:
        self.policy = json.loads(Path(policy_file).read_text(encoding="utf-8"))

    def evaluate(
        self,
        assessment: OperationalConfidenceAssessment,
    ) -> AutomationReadinessAssessment:
        thresholds = self.policy["thresholds"]
        selected = (
            assessment.candidate_assessments[0]
            if assessment.candidate_assessments
            else None
        )
        profile = selected.outcome_profile if selected else None
        known_error_id = assessment.selected_known_error_id
        control = self.policy.get("control_profiles", {}).get(
            known_error_id or "",
            {},
        )

        criteria = [
            ReadinessCriterion(
                criterion_id="CONFIDENCE",
                label="Operational confidence",
                passed=(
                    assessment.confidence_score
                    >= float(thresholds["minimum_confidence_score"])
                ),
                actual=assessment.confidence_score,
                required=thresholds["minimum_confidence_score"],
                explanation="Confidence must exceed the advisory policy threshold.",
            ),
            ReadinessCriterion(
                criterion_id="OUTCOME_SAMPLE",
                label="Comparable governed outcomes",
                passed=(
                    profile is not None
                    and profile.sample_size
                    >= int(thresholds["minimum_comparable_outcomes"])
                ),
                actual=profile.sample_size if profile else 0,
                required=thresholds["minimum_comparable_outcomes"],
                explanation="A mature evidence base is required before automation is considered.",
            ),
            ReadinessCriterion(
                criterion_id="RECENT_SUCCESS",
                label="Recent success rate",
                passed=(
                    profile is not None
                    and profile.recent_success_rate
                    >= float(thresholds["minimum_recent_success_rate"])
                ),
                actual=profile.recent_success_rate if profile else 0.0,
                required=thresholds["minimum_recent_success_rate"],
                explanation="Recent outcomes must remain consistently successful.",
            ),
            ReadinessCriterion(
                criterion_id="RECURRENCE",
                label="Recent recurrence rate",
                passed=(
                    profile is not None
                    and profile.recent_recurrence_rate
                    <= float(thresholds["maximum_recent_recurrence_rate"])
                ),
                actual=profile.recent_recurrence_rate if profile else 1.0,
                required=thresholds["maximum_recent_recurrence_rate"],
                explanation="Recovery must not create rapid recurrence.",
            ),
            ReadinessCriterion(
                criterion_id="DRIFT",
                label="Confidence drift",
                passed=(
                    assessment.drift_status
                    in set(self.policy["allowed_drift_statuses"])
                ),
                actual=assessment.drift_status,
                required=self.policy["allowed_drift_statuses"],
                explanation="Eroding confidence suspends automation readiness.",
            ),
            ReadinessCriterion(
                criterion_id="CONTRADICTION",
                label="Unresolved contradiction",
                passed=(
                    assessment.contradiction_level
                    <= float(thresholds["maximum_contradiction_level"])
                ),
                actual=assessment.contradiction_level,
                required=thresholds["maximum_contradiction_level"],
                explanation="Material unresolved contradictions require broader investigation.",
            ),
            ReadinessCriterion(
                criterion_id="REVERSIBLE",
                label="Action reversibility",
                passed=bool(control.get("reversible", False)),
                actual=bool(control.get("reversible", False)),
                required=True,
                explanation="The candidate action must be reversible.",
            ),
            ReadinessCriterion(
                criterion_id="BOUNDED_BLAST_RADIUS",
                label="Bounded blast radius",
                passed=bool(control.get("bounded_blast_radius", False)),
                actual=bool(control.get("bounded_blast_radius", False)),
                required=True,
                explanation="The action must remain within a bounded operational scope.",
            ),
            ReadinessCriterion(
                criterion_id="POLICY",
                label="Policy allows candidacy",
                passed=bool(control.get("policy_allows_candidate", False)),
                actual=bool(control.get("policy_allows_candidate", False)),
                required=True,
                explanation="Policy must explicitly allow the pattern to become a candidate.",
            ),
        ]

        suspension_flags = set(self.policy["suspension_hard_flags"])
        active_suspension_flags = sorted(
            suspension_flags.intersection(assessment.hard_flags)
        )
        blockers = [criterion.criterion_id for criterion in criteria if not criterion.passed]
        blockers.extend(active_suspension_flags)
        blockers = sorted(set(blockers))

        if active_suspension_flags or assessment.drift_status == "ERODING":
            status = "SUSPENDED"
        elif all(criterion.passed for criterion in criteria):
            status = "CANDIDATE"
        elif profile and profile.sample_size > 0:
            status = "BUILDING_EVIDENCE"
        else:
            status = "NOT_READY"

        explanation = (
            f"Automation readiness is {status}. Confidence is "
            f"{assessment.confidence_level} {assessment.confidence_score:.3f}; "
            f"{len(criteria) - len([c for c in criteria if not c.passed])} of "
            f"{len(criteria)} advisory criteria passed. Human approval remains "
            f"enforced in V1 regardless of readiness status."
        )

        return AutomationReadinessAssessment(
            status=status,
            advisory_only=bool(self.policy.get("advisory_only", True)),
            human_approval_enforced=bool(
                self.policy.get("human_approval_enforced", True)
            ),
            selected_known_error_id=known_error_id,
            confidence_score=assessment.confidence_score,
            confidence_level=assessment.confidence_level,
            criteria=criteria,
            blockers=blockers,
            required_constraints=list(control.get("required_constraints", [])),
            explanation=explanation,
        )

    @staticmethod
    def to_dict(result: AutomationReadinessAssessment) -> dict:
        return asdict(result)
