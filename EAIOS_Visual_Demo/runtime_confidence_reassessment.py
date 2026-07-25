from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
import json

from operational_confidence_engine import OperationalConfidenceAssessment
from runtime_evidence import RuntimeEvidenceSignal


@dataclass(frozen=True)
class ReassessmentResult:
    initial_confidence_score: float
    updated_confidence_score: float
    initial_confidence_level: str
    updated_confidence_level: str
    initial_drift_status: str
    updated_drift_status: str
    initial_contradiction_level: float
    updated_contradiction_level: float
    new_hard_flags: list[str]
    resolved_hard_flags: list[str]
    applied_penalty: float
    applied_credit: float
    credit_blocked_by_hard_flags: bool
    runtime_signal_types: list[str]
    explanation: str


class RuntimeConfidenceReassessor:
    """Apply policy-defined runtime signals to an existing confidence profile."""

    def __init__(
        self,
        signal_policy_file: str | Path,
        confidence_policy_file: str | Path,
    ) -> None:
        self.signal_policy = self._read(Path(signal_policy_file))
        self.confidence_policy = self._read(Path(confidence_policy_file))

    @staticmethod
    def _read(path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _level(self, score: float) -> str:
        levels = self.confidence_policy["levels"]
        if score >= float(levels["HIGH"]):
            return "HIGH"
        if score >= float(levels["MEDIUM"]):
            return "MEDIUM"
        return "LOW"

    def reassess(
        self,
        initial: OperationalConfidenceAssessment,
        signals: list[RuntimeEvidenceSignal],
    ) -> tuple[OperationalConfidenceAssessment, ReassessmentResult]:
        limits = self.signal_policy.get("limits", {})
        maximum_credit = float(
            limits.get("maximum_credit_per_reassessment", 0.0)
        )
        runtime_ceiling = float(limits.get("maximum_runtime_confidence", 1.0))
        credits_need_clean_flags = bool(
            limits.get("credits_require_no_unresolved_hard_flags", True)
        )

        penalty = 0.0
        credit = 0.0
        contradiction_increment = 0.0
        contradiction_decrement = 0.0
        drift_status = initial.drift_status
        hard_flags = set(initial.hard_flags)
        resolver_flags: set[str] = set()
        signal_types = []

        for signal in signals:
            configuration = self.signal_policy["signals"].get(
                signal.signal_type
            )
            if not configuration:
                continue
            signal_types.append(signal.signal_type)
            penalty += float(configuration.get("confidence_penalty", 0.0))
            credit += float(configuration.get("confidence_credit", 0.0))
            contradiction_increment += float(
                configuration.get("contradiction_increment", 0.0)
            )
            contradiction_decrement += float(
                configuration.get("contradiction_decrement", 0.0)
            )
            forced_drift = configuration.get("force_drift_status")
            if forced_drift:
                drift_status = forced_drift
            if configuration.get("hard_flag"):
                hard_flags.add(signal.signal_type)
            resolver_flags.update(
                configuration.get("resolves_flags", []) or []
            )

        if not signal_types:
            signal_types = ["DUE_DILIGENCE_PASSED"]

        # A hard flag clears only when a signal names it explicitly. Nothing
        # is resolved implicitly by improved scores or elapsed execution.
        resolved_flags = hard_flags & resolver_flags
        hard_flags -= resolver_flags

        # Asymmetry: penalties apply in full and immediately, credits are
        # capped per reassessment and are withheld entirely while any hard
        # flag remains unresolved. Confidence stays hard to gain, easy to lose.
        applied_credit = min(credit, maximum_credit)
        # "Blocked" means credit was earned and then denied. Signals that
        # never offered credit are not reported as having lost any.
        credit_blocked = (
            credits_need_clean_flags
            and bool(hard_flags)
            and applied_credit > 0.0
        )
        if credit_blocked:
            applied_credit = 0.0

        updated_score = initial.confidence_score - penalty + applied_credit
        if applied_credit > 0.0:
            # Runtime evidence can restore confidence, but never to the level
            # earned by an outcome-validated known error.
            updated_score = min(updated_score, runtime_ceiling)
        updated_score = max(0.0, min(1.0, updated_score))

        updated_contradiction = max(
            0.0,
            min(
                1.0,
                initial.contradiction_level
                + contradiction_increment
                - contradiction_decrement,
            ),
        )
        updated_level = self._level(updated_score)
        if drift_status == "ERODING" or updated_score < initial.confidence_score:
            trend = "ERODING"
        elif updated_score > initial.confidence_score:
            trend = "IMPROVING"
        else:
            trend = initial.confidence_trend

        updated = replace(
            initial,
            confidence_score=round(updated_score, 3),
            confidence_level=updated_level,
            confidence_trend=trend,
            drift_status=drift_status,
            contradiction_level=round(updated_contradiction, 3),
            hard_flags=sorted(hard_flags),
            explanation=(
                f"{initial.explanation} Runtime reassessment processed "
                f"{len(signals)} new signal(s): {signal_types}. "
                f"Confidence changed from {initial.confidence_score:.3f} "
                f"to {updated_score:.3f}."
            ),
        )

        result = ReassessmentResult(
            initial_confidence_score=initial.confidence_score,
            updated_confidence_score=round(updated_score, 3),
            initial_confidence_level=initial.confidence_level,
            updated_confidence_level=updated_level,
            initial_drift_status=initial.drift_status,
            updated_drift_status=drift_status,
            initial_contradiction_level=initial.contradiction_level,
            updated_contradiction_level=round(updated_contradiction, 3),
            new_hard_flags=sorted(
                set(updated.hard_flags) - set(initial.hard_flags)
            ),
            resolved_hard_flags=sorted(resolved_flags),
            applied_penalty=round(penalty, 3),
            applied_credit=round(applied_credit, 3),
            credit_blocked_by_hard_flags=credit_blocked,
            runtime_signal_types=signal_types,
            explanation=(
                f"Applied policy-defined runtime evidence. "
                f"Level {initial.confidence_level} → {updated_level}; "
                f"drift {initial.drift_status} → {drift_status}."
                + self._asymmetry_note(
                    applied_credit, credit_blocked, resolved_flags
                )
            ),
        )
        return updated, result

    @staticmethod
    def _asymmetry_note(
        applied_credit: float,
        credit_blocked: bool,
        resolved_flags: set[str],
    ) -> str:
        """Describe credit and resolver activity, silent when neither occurred."""
        notes = []
        if resolved_flags:
            notes.append(f"Resolved hard flags: {sorted(resolved_flags)}.")
        if credit_blocked:
            notes.append(
                "Confidence credit withheld while hard flags remain unresolved."
            )
        elif applied_credit > 0.0:
            notes.append(f"Applied confidence credit {applied_credit:.3f}.")
        return (" " + " ".join(notes)) if notes else ""

    @staticmethod
    def to_dict(result: ReassessmentResult) -> dict:
        return asdict(result)
