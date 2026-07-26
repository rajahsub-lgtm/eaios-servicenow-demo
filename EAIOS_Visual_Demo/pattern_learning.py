"""Turn a validated proposal into experience, and a rejected one into evidence.

A proposal read from a manual and put to a human has one of three fates. It is
confirmed, in which case the system has learned a pattern it did not have. It
is corrected, in which case it has learned a better one, and the correction is
the most informative thing that happened. Or it is rejected, in which case it
has learned that this account did not hold here.

Rejection lowers what the account is worth. It does not remove it. A human can
reject correctly and a human can reject wrongly, and a system that treats one
rejection as permanent has made a person's error unfalsifiable — the same
asymmetry the rest of this system refuses everywhere else. So a refuted
hypothesis stays proposable, ranked lower, with its refutation disclosed; if
nothing better exists it will be offered again, and the human will be told it
was rejected before and by whom.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json


VALIDATION_DECISIONS = ("CONFIRMED", "CORRECTED", "REJECTED")


@dataclass(frozen=True)
class ValidationDecision:
    """What a human concluded about a proposed cause."""

    decision: str
    validated_by: str
    decided_at: str
    reason: str = ""
    corrected_cause: str = ""
    corrected_action: str = ""

    def __post_init__(self) -> None:
        if self.decision not in VALIDATION_DECISIONS:
            raise ValueError(
                f"decision must be one of {VALIDATION_DECISIONS}, "
                f"got {self.decision!r}"
            )


@dataclass(frozen=True)
class Refutation:
    refutation_id: str
    hypothesis_id: str
    entity_id: str
    symptom_categories: list[str]
    rejected_by: str
    reason: str
    recorded_at: str
    data_classification: str = "SYNTHETIC"


@dataclass(frozen=True)
class LearnedPattern:
    """A known error the system was not given but arrived at.

    Carries the same fields as a curated known error so every downstream layer
    treats it identically, plus the provenance of how it came to exist. It is
    marked Provisional: one validated case is a pattern in the making, not an
    established one, and nothing should mistake it for the latter.
    """

    known_error_id: str
    title: str
    applies_to_entity_id: str
    external_service_id: str
    symptom_category: str
    trigger_metric_id: str
    probable_cause: str
    recommended_action: str
    knowledge_status: str
    trust_level: str
    historical_occurrences: int
    historical_success_rate_numeric: float
    recent_failure_signal: str
    average_resolution_minutes: float
    requires_human_approval: bool
    valid_from: str
    valid_to: str
    data_classification: str
    hypothesis_class: str
    learned_from_document_id: str
    validated_by: str
    validation_decision: str
    learned_at: str


class JsonListStore:
    """Append-only JSON list with an identity check, as used for feedback."""

    def __init__(self, path: str | Path, *, id_field: str) -> None:
        self.path = Path(path)
        self.id_field = id_field
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def list(self) -> list[dict[str, Any]]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def append(self, record) -> bool:
        rows = self.list()
        payload = asdict(record) if hasattr(record, "__dataclass_fields__") else dict(record)
        if any(
            row.get(self.id_field) == payload[self.id_field] for row in rows
        ):
            return False
        rows.append(payload)
        self.path.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return True


class PatternLearner:
    """Record what validation established, in the form the system already reads.

    Nothing here invents a new storage concept. A learned pattern is written as
    a known error and a validated case as an outcome record, because the whole
    point is that the next encounter meets it through the ordinary recall path
    rather than a special one.
    """

    def __init__(self, json_dir: str | Path) -> None:
        self.json_dir = Path(json_dir)
        self.patterns = JsonListStore(
            self.json_dir / "learned_patterns.json", id_field="known_error_id"
        )
        self.refutations = JsonListStore(
            self.json_dir / "refutation_ledger.json", id_field="refutation_id"
        )

    @staticmethod
    def _slug(entity_id: str, symptom: str) -> str:
        entity = entity_id.replace("COMP-", "").replace("AS-", "")
        return f"KE-LEARNED-{entity}-{symptom}"[:60]

    def learn(
        self,
        *,
        assessment,
        decision: ValidationDecision,
        fingerprint,
        document_id: str,
        proposed_cause: str,
        proposed_action: str,
        trigger_metric_id: str = "",
        external_service_id: str = "",
    ) -> LearnedPattern | Refutation:
        """Record the validation outcome and return what it produced."""
        symptom = (
            fingerprint.symptom_categories[0]
            if fingerprint.symptom_categories
            else "UNCLASSIFIED"
        )
        if decision.decision == "REJECTED":
            refutation = Refutation(
                refutation_id=(
                    f"REF-{document_id}-{fingerprint.entity_id}-"
                    f"{decision.decided_at[:10]}"
                ),
                hypothesis_id=document_id,
                entity_id=fingerprint.entity_id,
                symptom_categories=list(fingerprint.symptom_categories),
                rejected_by=decision.validated_by,
                reason=decision.reason,
                recorded_at=decision.decided_at,
            )
            self.refutations.append(refutation)
            return refutation

        corrected = decision.decision == "CORRECTED"
        pattern = LearnedPattern(
            known_error_id=self._slug(fingerprint.entity_id, symptom),
            title=(
                f"{fingerprint.entity_id.replace('COMP-', '').title()} "
                f"{symptom.replace('_', ' ').lower()}"
            ),
            applies_to_entity_id=fingerprint.entity_id,
            # A learned pattern must be as well-formed as a curated one, or it
            # scores poorly on dimensions that have nothing to do with its
            # newness — the trigger metric and service linkage are how the
            # assessment establishes that a pattern is about this signal at
            # all, and omitting them penalises the pattern for the learner's
            # sloppiness rather than for its thin evidence.
            external_service_id=external_service_id,
            symptom_category=symptom,
            trigger_metric_id=trigger_metric_id,
            probable_cause=(
                decision.corrected_cause if corrected else proposed_cause
            ),
            recommended_action=(
                decision.corrected_action if corrected else proposed_action
            ),
            # One validated case is a pattern in the making. Anything that
            # reads knowledge_status can see it has not earned Active.
            knowledge_status="Provisional",
            trust_level="Provisional",
            historical_occurrences=1,
            historical_success_rate_numeric=0.0,
            recent_failure_signal="UNKNOWN",
            average_resolution_minutes=0.0,
            requires_human_approval=True,
            valid_from=decision.decided_at[:10],
            valid_to="",
            data_classification="SYNTHETIC",
            hypothesis_class="LEARNED",
            learned_from_document_id=document_id,
            validated_by=decision.validated_by,
            validation_decision=decision.decision,
            learned_at=decision.decided_at,
        )
        self.patterns.append(pattern)
        return pattern

    def refutations_for(
        self, *, hypothesis_id: str, entity_id: str
    ) -> list[dict[str, Any]]:
        """Rejections recorded against this account of this component."""
        return [
            row
            for row in self.refutations.list()
            if row.get("hypothesis_id") == hypothesis_id
            and row.get("entity_id") == entity_id
        ]
