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
        penalty = 0.0
        contradiction_increment = 0.0
        drift_status = initial.drift_status
        hard_flags = set(initial.hard_flags)
        signal_types = []

        for signal in signals:
            configuration = self.signal_policy["signals"].get(
                signal.signal_type
            )
            if not configuration:
                continue
            signal_types.append(signal.signal_type)
            penalty += float(configuration.get("confidence_penalty", 0.0))
            contradiction_increment += float(
                configuration.get("contradiction_increment", 0.0)
            )
            forced_drift = configuration.get("force_drift_status")
            if forced_drift:
                drift_status = forced_drift
            if configuration.get("hard_flag"):
                hard_flags.add(signal.signal_type)

        if not signal_types:
            signal_types = ["DUE_DILIGENCE_PASSED"]

        updated_score = max(0.0, initial.confidence_score - penalty)
        updated_contradiction = min(
            1.0,
            initial.contradiction_level + contradiction_increment,
        )
        updated_level = self._level(updated_score)
        trend = (
            "ERODING"
            if updated_score < initial.confidence_score or drift_status == "ERODING"
            else initial.confidence_trend
        )

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
            runtime_signal_types=signal_types,
            explanation=(
                f"Applied policy-defined runtime evidence. "
                f"Level {initial.confidence_level} → {updated_level}; "
                f"drift {initial.drift_status} → {drift_status}."
            ),
        )
        return updated, result

    @staticmethod
    def to_dict(result: ReassessmentResult) -> dict:
        return asdict(result)
