"""Reason from the manual when nothing has ever been tried.

An experienced practitioner meeting a presentation they have never seen does
not stop. They reach for the written procedure, form a provisional account of
what is happening, and put it to someone who can validate it. That is not the
same as knowing, and the difference has to survive into the output: a proposal
drawn from a document is a hypothesis awaiting confirmation, not a diagnosis.

The governed non-diagnosis this replaces was honest but terminal — it declined
to guess and left the case with nowhere to go, so no first encounter could ever
become a second one. This module gives the first encounter a way forward that
is still explicitly not experience.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json

from case_fingerprint import CaseFingerprint


@dataclass(frozen=True)
class DocumentedHypothesis:
    """A cause proposed from documentation, with its source named."""

    document_id: str
    title: str
    document_type: str
    owner: str
    trust_level: str
    probable_cause: str
    recommended_action: str
    support: float
    symptom_coverage: float
    freshness_credit: float
    days_since_validation: int
    dimensions: dict[str, float]
    reasons: tuple[str, ...]


def _split(value) -> tuple[str, ...]:
    """Fixtures store these as either a comma-joined string or a list."""
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return tuple(
        part.strip() for part in str(value or "").split(",") if part.strip()
    )


def resolve_documentation_policy(json_dir: str | Path) -> Path:
    """Find the policy for a fixture directory, falling back to the shipped one.

    Tests copy fixtures to temporary locations without the config tree; where a
    fixture was copied to should not change how it behaves.
    """
    candidate = Path(json_dir).parent / "config" / "documentation_policy.json"
    if candidate.exists():
        return candidate
    return (
        Path(__file__).resolve().parent / "config" / "documentation_policy.json"
    )


class DocumentationReasoner:
    def __init__(
        self, json_dir: str | Path, policy_file: str | Path | None = None
    ) -> None:
        self.json_dir = Path(json_dir)
        path = Path(policy_file) if policy_file else resolve_documentation_policy(
            self.json_dir
        )
        self.policy = json.loads(path.read_text(encoding="utf-8"))
        self.eligibility = self.policy["eligibility"]
        self.weights = self.policy["support_weights"]
        self.ceiling = self.policy["ceiling"]
        with open(
            self.json_dir / "knowledge_documents.json", encoding="utf-8"
        ) as f:
            self.documents = json.load(f)

    @property
    def maximum_confidence(self) -> float:
        return float(self.ceiling["maximum_documented_confidence"])

    def _freshness(self, document: dict, assessed_at: datetime) -> tuple[float, int]:
        raw = str(document.get("last_validated_at", "")).strip()
        if not raw:
            return 0.0, -1
        try:
            validated = datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            return 0.0, -1
        days = max(0, (assessed_at - validated).days)
        full = float(self.policy["freshness"]["full_credit_days"])
        none = float(self.policy["freshness"]["no_credit_days"])
        if days <= full:
            return 1.0, days
        if days >= none:
            return 0.0, days
        return round(1.0 - (days - full) / (none - full), 3), days

    def _eligible(self, document: dict, case: CaseFingerprint) -> bool:
        if document.get("status") != self.eligibility["required_status"]:
            return False
        if (
            document.get("content_safety_status")
            != self.eligibility["required_content_safety_status"]
        ):
            return False
        if self.eligibility.get("require_entity_match", True):
            if case.entity_id not in set(_split(document.get("entity_ids"))):
                return False
        return True

    def _symptom_coverage(self, document: dict, case: CaseFingerprint) -> float:
        presenting = set(case.symptom_categories)
        if not presenting:
            return 0.0
        documented = set(_split(document.get("symptom_categories")))
        return len(presenting & documented) / len(presenting)

    def propose(
        self, case: CaseFingerprint, *, assessed_at: datetime
    ) -> list[DocumentedHypothesis]:
        """Rank the documents that could account for this presentation."""
        proposals: list[DocumentedHypothesis] = []
        for document in self.documents:
            if not self._eligible(document, case):
                continue
            coverage = self._symptom_coverage(document, case)
            if coverage < float(self.eligibility["minimum_symptom_coverage"]):
                continue

            trust = float(
                self.policy["trust_weights"].get(
                    document.get("trust_level", "Unverified"), 0.0
                )
            )
            kind = float(
                self.policy["document_type_weights"].get(
                    document.get("document_type", "WIKI"), 0.3
                )
            )
            freshness, days = self._freshness(document, assessed_at)
            dimensions = {
                "symptom_coverage": coverage,
                "document_trust": trust,
                "document_type": kind,
                "freshness": freshness,
            }
            support = round(
                sum(
                    value * float(self.weights.get(name, 0.0))
                    for name, value in dimensions.items()
                ),
                3,
            )
            if trust <= 0.0:
                # A deprecated procedure is not a weak basis for a proposal,
                # it is a withdrawn one.
                continue

            reasons = []
            reasons.append(
                "SYMPTOM_FULLY_DOCUMENTED"
                if coverage >= 0.999
                else "SYMPTOM_PARTIALLY_DOCUMENTED"
            )
            reasons.append(f"TRUST_{str(document.get('trust_level','')).upper()}")
            reasons.append(f"TYPE_{str(document.get('document_type','')).upper()}")
            if freshness >= 0.999:
                reasons.append("RECENTLY_VALIDATED")
            elif freshness <= 0.0:
                reasons.append("VALIDATION_LAPSED")
            else:
                reasons.append("VALIDATION_AGEING")
            reasons.append("NO_RECORDED_EXPERIENCE")

            proposals.append(
                DocumentedHypothesis(
                    document_id=document["document_id"],
                    title=document.get("title", ""),
                    document_type=document.get("document_type", ""),
                    owner=document.get("owner", "Unassigned"),
                    trust_level=document.get("trust_level", "Unverified"),
                    # The document's own words. Nothing is invented here; a
                    # proposal a human cannot trace to a source is a proposal
                    # they cannot validate.
                    probable_cause=(
                        str(document.get("body", "")).strip()
                        or str(document.get("recommended_action", "")).strip()
                    ),
                    recommended_action=str(
                        document.get("recommended_action", "")
                    ).strip(),
                    support=support,
                    symptom_coverage=round(coverage, 3),
                    freshness_credit=freshness,
                    days_since_validation=days,
                    dimensions={k: round(v, 3) for k, v in dimensions.items()},
                    reasons=tuple(reasons),
                )
            )

        proposals.sort(key=lambda item: (-item.support, item.document_id))
        return proposals

    def confidence_for(self, proposal: DocumentedHypothesis) -> float:
        """Confidence a documented proposal is allowed to carry.

        Held below the band that would let it narrow a plan. Trust in a
        document is trust in its author; it is not evidence that the procedure
        works on this system, and only an outcome can supply that.

        Support is scaled into the permitted band rather than clipped at it.
        Clipping would hand a current, trusted runbook and a lapsed wiki page
        the same confidence the moment both cleared the ceiling, discarding the
        one judgement this reasoner exists to make.
        """
        return round(proposal.support * self.maximum_confidence, 3)
