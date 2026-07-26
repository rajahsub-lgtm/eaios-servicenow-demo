"""The one place that answers what the system has experienced.

Two questions were being answered independently by the confidence engine and
the evidence fusion agent, and they kept reaching different answers:

  * **What history counts for a pattern** — which outcome rows, and what each
    is worth. The engine weighted by recency and provenance; fusion counted
    raw. Over the same twenty queue cases that was 0.47 against 0.55, so the
    number a human read was not the number that chose the plan.

  * **Which patterns are recallable** — the knowledge-status and trust filters,
    written out in both modules. They diverged once already, making a learned
    pattern visible to the planner and invisible to the explainer.

Both are operational judgements about experience, so both live here and each
layer reads through this rather than deciding for itself. The layers keep
their own shapes on top: the engine builds a profile with drift and
supervision, fusion builds a summary for the explanation. What they must not
do is disagree about the underlying facts.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence
import json


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class ExperienceLedger:
    def __init__(
        self,
        json_dir: str | Path,
        *,
        confidence_policy: dict,
        trust_policy: dict,
        agent_registry: dict | None = None,
    ) -> None:
        self.json_dir = Path(json_dir)
        self.policy = confidence_policy
        self.trust_policy = trust_policy
        self.agent_registry = agent_registry or {}
        self.maturity = trust_policy["pattern_maturity"]

    # -- loading -----------------------------------------------------------

    @staticmethod
    def load_outcomes(json_dir: str | Path) -> list[dict]:
        """Every recorded case, including what was learned at runtime.

        Fusion read only the shipped history for the whole of its existence,
        so a pattern could accumulate cases that the planner could see and the
        explainer could not.
        """
        json_dir = Path(json_dir)
        with open(json_dir / "outcome_history.json", encoding="utf-8") as f:
            rows = json.load(f)
        feedback = json_dir / "runtime_outcome_feedback.json"
        if feedback.exists():
            with open(feedback, encoding="utf-8") as f:
                extra = json.load(f)
            if not isinstance(extra, list):
                raise ValueError(
                    "runtime_outcome_feedback.json must contain a JSON array."
                )
            rows.extend(extra)
        return rows

    @staticmethod
    def load_patterns(json_dir: str | Path) -> list[dict]:
        """Curated known errors plus patterns the system arrived at itself."""
        json_dir = Path(json_dir)
        with open(json_dir / "known_errors.json", encoding="utf-8") as f:
            rows = json.load(f)
        learned = json_dir / "learned_patterns.json"
        if learned.exists():
            with open(learned, encoding="utf-8") as f:
                rows.extend(json.load(f))
        return rows

    # -- admissibility -----------------------------------------------------

    def is_admissible(self, pattern: dict, assessed_at: datetime) -> bool:
        """Whether this pattern may be recalled at all.

        Admissibility and worth are different questions. Provisional patterns
        are admitted here and discounted later; excluding them made a learned
        pattern unrecallable and so unable to ever mature.
        """
        if pattern.get("knowledge_status") not in set(
            self.maturity["admissible_knowledge_statuses"]
        ):
            return False
        if pattern.get("trust_level") not in set(
            self.maturity["admissible_trust_levels"]
        ):
            return False
        valid_from = pattern.get("valid_from", "")
        if valid_from and datetime.strptime(valid_from, "%Y-%m-%d") > assessed_at:
            return False
        valid_to = pattern.get("valid_to", "")
        if valid_to and datetime.strptime(valid_to, "%Y-%m-%d") < assessed_at:
            return False
        return True

    def admissible(
        self, patterns: Iterable[dict], assessed_at: datetime
    ) -> list[dict]:
        return [
            pattern
            for pattern in patterns
            if self.is_admissible(pattern, assessed_at)
        ]

    # -- history -----------------------------------------------------------

    @staticmethod
    def _dt(value: str) -> datetime:
        return datetime.strptime(value, DATETIME_FORMAT)

    def rows_for(
        self,
        outcomes: Sequence[dict],
        known_error_id: str,
        assessed_at: datetime,
    ) -> list[dict]:
        """Cases recorded against this pattern, on or before the assessment.

        Matched on the pattern's identity alone. Fusion additionally required
        scenario_pattern to match, which was redundant on the shipped fixtures
        and silently wrong for anything recorded at runtime.
        """
        rows = [
            row
            for row in outcomes
            if row.get("known_error_id") == known_error_id
            and self._dt(row["recorded_at"]) <= assessed_at
        ]
        rows.sort(key=lambda row: self._dt(row["recorded_at"]))
        return rows

    def provenance_of(self, row: dict) -> str:
        """How this case came to be known.

        Derived from what the record already holds. A human who amended or
        overruled a recommendation engaged with the case, which is not the
        same as one who waved it through.
        """
        if row.get("established_by_agent"):
            return "PEER_AGENT"
        if str(row.get("approval_decision", "")).lower() in {
            "rejected",
            "declined",
        }:
            return "HUMAN_VERIFIED"
        if str(row.get("human_modification", "None")).strip() not in {
            "",
            "None",
        }:
            return "HUMAN_VERIFIED"
        return "SELF_OUTCOME"

    def provenance_weight(self, row: dict) -> float:
        """Trust in the source, attenuated by its standing over the claim."""
        provenance = self.provenance_of(row)
        weights = self.trust_policy["provenance_weights"]
        weight = float(weights.get(provenance, 1.0))
        if provenance != "PEER_AGENT":
            return weight

        standing = self.trust_policy["standing"]
        attenuation = self.trust_policy["attenuation"]
        agent = self.agent_registry.get(row.get("established_by_agent", ""), {})
        reliability = float(agent.get("reliability_score", 0.5))
        claimed = row.get("established_for_domain", "")
        if standing.get("enforce_domain_standing", True) and claimed:
            if claimed not in set(agent.get("data_domains", [])):
                # Reliable, but speaking outside its remit.
                return weight * float(standing["out_of_standing_weight"])
        # Trust never amplifies on transfer.
        return min(weight * reliability, float(attenuation["maximum_peer_trust"]))

    def weights_for(
        self, rows: Sequence[dict], assessed_at: datetime
    ) -> list[float]:
        """Recency decay multiplied by what the source is worth."""
        weighting = self.policy["recency_weighting"]
        half_life = float(weighting["half_life_days"])
        enabled = weighting.get("enabled", True)
        weights = []
        for row in rows:
            if enabled:
                age_days = max(
                    0.0,
                    (assessed_at - self._dt(row["recorded_at"])).total_seconds()
                    / 86400,
                )
                recency = 0.5 ** (age_days / half_life)
            else:
                recency = 1.0
            weights.append(recency * self.provenance_weight(row))
        return weights

    def weighted_average(
        self, values: Sequence[float], weights: Sequence[float]
    ) -> float:
        denominator = sum(weights)
        if not denominator:
            return 0.0
        return sum(v * w for v, w in zip(values, weights)) / denominator

    def success_rate(
        self, rows: Sequence[dict], assessed_at: datetime
    ) -> float:
        """The single figure both layers must quote.

        A declined recommendation is not a success: counting an action nobody
        performed as one is how a success rate stops meaning anything.
        """
        if not rows:
            return 0.0
        weights = self.weights_for(rows, assessed_at)
        return round(
            self.weighted_average(
                [1.0 if row["outcome"] == "Successful" else 0.0 for row in rows],
                weights,
            ),
            3,
        )

    def recurrence_rate(
        self, rows: Sequence[dict], assessed_at: datetime
    ) -> float:
        if not rows:
            return 1.0
        return round(
            self.weighted_average(
                [1.0 if row["recurrence_within_24h"] else 0.0 for row in rows],
                self.weights_for(rows, assessed_at),
            ),
            3,
        )

    def provenance_mix(self, rows: Sequence[dict]) -> dict[str, int]:
        return {
            name: sum(1 for row in rows if self.provenance_of(row) == name)
            for name in ("SELF_OUTCOME", "HUMAN_VERIFIED", "PEER_AGENT")
        }
