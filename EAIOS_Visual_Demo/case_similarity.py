from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from case_fingerprint import CaseFingerprint


@dataclass(frozen=True)
class SimilarityAssessment:
    """How alike two presentations are, and on what grounds."""

    score: float
    is_direct: bool
    dimensions: dict[str, float]
    reasons: list[str]

    @property
    def is_transferred(self) -> bool:
        return self.score > 0.0 and not self.is_direct


def _overlap(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    """Jaccard overlap; empty on both sides counts as no evidence, not a match."""
    a, b = set(left), set(right)
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


class CaseSimilarity:
    """Score how alike two cases are, by presentation rather than label.

    Applicability used to be a boolean: does an APPLIES_TO edge reach this
    entity. That answered yes for a familiar component showing an unfamiliar
    symptom, and no for an identical symptom on a structural sibling — the two
    failure modes are opposite and both wrong.

    Scoring instead lets a match be partial, which is what the situation
    usually is. Weights live in policy because how alike is alike enough is an
    operational judgement, not an engineering constant.
    """

    def __init__(self, policy_file: str | Path) -> None:
        self.policy = json.loads(Path(policy_file).read_text(encoding="utf-8"))
        self.weights = self.policy["dimension_weights"]
        self.thresholds = self.policy["thresholds"]
        self.transfer = self.policy["transfer"]

    @property
    def floor(self) -> float:
        return float(self.thresholds["minimum_similarity_to_consider"])

    def compare(
        self, case: CaseFingerprint, remembered: CaseFingerprint
    ) -> SimilarityAssessment:
        same_entity = 1.0 if case.entity_id == remembered.entity_id else 0.0
        symptom = _overlap(case.symptom_categories, remembered.symptom_categories)
        # Structural position: sharing a parent service and sharing dependencies
        # both indicate the same role in the architecture.
        structural = 0.5 * _overlap(
            case.parent_services, remembered.parent_services
        ) + 0.5 * _overlap(case.depends_on, remembered.depends_on)
        kind = (
            1.0
            if case.entity_type
            and case.entity_type == remembered.entity_type
            else 0.0
        )
        capability = _overlap(
            case.impacted_capabilities, remembered.impacted_capabilities
        )
        severity = (
            1.0
            if case.severity_band != "NONE"
            and case.severity_band == remembered.severity_band
            else 0.0
        )

        dimensions = {
            "same_entity": same_entity,
            "symptom_overlap": symptom,
            "structural_position": structural,
            "entity_kind": kind,
            "capability_overlap": capability,
            "severity_band": severity,
        }
        score = sum(
            value * float(self.weights.get(name, 0.0))
            for name, value in dimensions.items()
        )
        score = round(min(1.0, score), 3)

        direct = (
            same_entity == 1.0
            and symptom >= 0.999
        )
        if not direct:
            # An analogy is never allowed to count as firsthand.
            score = round(
                min(score, float(self.transfer["maximum_transferred_similarity"])), 3
            )

        reasons = []
        if same_entity:
            reasons.append("SAME_ENTITY")
        elif structural > 0.4:
            reasons.append("STRUCTURAL_SIBLING")
        if symptom >= 0.999:
            reasons.append("SAME_SYMPTOM")
        elif symptom > 0:
            reasons.append("PARTIAL_SYMPTOM_OVERLAP")
        else:
            reasons.append("SYMPTOM_DIVERGENCE")
        if direct:
            reasons.append("DIRECT_EXPERIENCE")
        elif score >= self.floor:
            reasons.append("TRANSFERRED_EXPERIENCE")
        else:
            reasons.append("BELOW_SIMILARITY_FLOOR")

        return SimilarityAssessment(
            score=score, is_direct=direct, dimensions=dimensions, reasons=reasons
        )
