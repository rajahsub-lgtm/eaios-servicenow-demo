from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Iterable
import json


TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class MetricSummary:
    metric_id: str
    metric_name: str
    entity_id: str
    unit: str
    sample_count: int
    baseline_value: float
    latest_value: float
    peak_value: float
    peak_at: str
    warning_threshold: float
    critical_threshold: float
    first_warning_at: str | None
    first_critical_at: str | None
    change_from_baseline_percent: float | None
    trend: str
    current_status: str
    source_system: str
    trust_level: str


@dataclass(frozen=True)
class TimelineEvent:
    observed_at: str
    event_type: str
    metric_id: str
    metric_name: str
    entity_id: str
    value: float
    threshold: float
    unit: str
    source_system: str
    trust_level: str


@dataclass(frozen=True)
class TelemetryAssessment:
    scenario_id: str
    scenario_name: str
    trigger_observation_id: str
    trigger_observed_at: str
    analysis_window_start: str
    analysis_window_end: str
    future_samples_excluded: int
    metric_summaries: list[MetricSummary]
    timeline: list[TimelineEvent]
    leading_signals: list[TimelineEvent]
    trigger_metric_summary: MetricSummary
    temporal_explanation: str


class TelemetryAnalysisAgent:
    """Deterministic, provenance-aware telemetry analysis for Hybrid EAIOS."""

    def __init__(self, json_dir: str | Path) -> None:
        json_dir = Path(json_dir)
        self.scenarios = self._load(json_dir / "scenarios.json")
        self.metric_definitions = self._load(json_dir / "metric_definitions.json")
        self.telemetry_samples = self._load(json_dir / "telemetry_samples.json")
        self.health_observations = self._load(json_dir / "health_observations.json")

        self.scenario_by_id = {row["scenario_id"]: row for row in self.scenarios}
        self.metric_by_id = {row["metric_id"]: row for row in self.metric_definitions}
        self.observation_by_id = {
            row["observation_id"]: row for row in self.health_observations
        }

    @staticmethod
    def _load(path: Path) -> list[dict]:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _dt(value: str) -> datetime:
        return datetime.strptime(value, TIME_FORMAT)

    def analyze(self, scenario_id: str) -> TelemetryAssessment:
        try:
            scenario = self.scenario_by_id[scenario_id]
        except KeyError as exc:
            raise KeyError(f"Unknown scenario: {scenario_id}") from exc

        trigger_id = scenario["trigger_observation_id"]
        trigger = self.observation_by_id[trigger_id]
        trigger_time = self._dt(trigger["observed_at"])

        all_samples = [
            row for row in self.telemetry_samples
            if row["scenario_id"] == scenario_id
        ]
        if not all_samples:
            raise ValueError(f"No telemetry samples found for {scenario_id}")

        # Prevent future-data leakage: analyze only evidence available at trigger time.
        eligible = [
            row for row in all_samples
            if self._dt(row["observed_at"]) <= trigger_time
        ]
        excluded = len(all_samples) - len(eligible)

        grouped: dict[tuple[str, str], list[dict]] = {}
        for row in eligible:
            grouped.setdefault((row["metric_id"], row["entity_id"]), []).append(row)

        summaries: list[MetricSummary] = []
        timeline: list[TimelineEvent] = []

        for (metric_id, entity_id), rows in grouped.items():
            rows.sort(key=lambda r: self._dt(r["observed_at"]))
            metric = self.metric_by_id[metric_id]
            values = [float(row["value"]) for row in rows]
            baseline_count = min(3, len(values))
            baseline = mean(values[:baseline_count])
            latest = values[-1]
            peak_row = max(rows, key=lambda row: float(row["value"]))

            first_warning = next(
                (
                    row for row in rows
                    if float(row["value"]) >= float(metric["warning_threshold"])
                ),
                None,
            )
            first_critical = next(
                (
                    row for row in rows
                    if float(row["value"]) >= float(metric["critical_threshold"])
                ),
                None,
            )

            if first_warning:
                timeline.append(
                    self._event(
                        first_warning,
                        "WARNING_THRESHOLD_CROSSED",
                        float(metric["warning_threshold"]),
                    )
                )
            if first_critical:
                timeline.append(
                    self._event(
                        first_critical,
                        "CRITICAL_THRESHOLD_CROSSED",
                        float(metric["critical_threshold"]),
                    )
                )

            pct_change = None
            if baseline != 0:
                pct_change = round(((latest - baseline) / abs(baseline)) * 100, 2)

            trend = self._trend(values)
            current_status = self._status(latest, metric)

            summaries.append(
                MetricSummary(
                    metric_id=metric_id,
                    metric_name=metric["name"],
                    entity_id=entity_id,
                    unit=metric["unit"],
                    sample_count=len(rows),
                    baseline_value=round(baseline, 2),
                    latest_value=round(latest, 2),
                    peak_value=round(float(peak_row["value"]), 2),
                    peak_at=peak_row["observed_at"],
                    warning_threshold=float(metric["warning_threshold"]),
                    critical_threshold=float(metric["critical_threshold"]),
                    first_warning_at=(
                        first_warning["observed_at"] if first_warning else None
                    ),
                    first_critical_at=(
                        first_critical["observed_at"] if first_critical else None
                    ),
                    change_from_baseline_percent=pct_change,
                    trend=trend,
                    current_status=current_status,
                    source_system=rows[-1]["source_system"],
                    trust_level=rows[-1]["trust_level"],
                )
            )

        summaries.sort(
            key=lambda s: (
                s.first_warning_at or "9999-12-31 23:59:59",
                s.metric_name,
            )
        )
        timeline.sort(
            key=lambda event: (
                self._dt(event.observed_at),
                0 if event.event_type.startswith("WARNING") else 1,
                event.metric_name,
            )
        )

        trigger_metric_id = trigger["metric_id"]
        matching_trigger_summaries = [
            summary for summary in summaries
            if summary.metric_id == trigger_metric_id
            and summary.entity_id == trigger["entity_id"]
        ]
        if len(matching_trigger_summaries) != 1:
            raise RuntimeError(
                f"Expected one trigger metric summary; found "
                f"{len(matching_trigger_summaries)}"
            )
        trigger_summary = matching_trigger_summaries[0]

        leading = [
            event for event in timeline
            if self._dt(event.observed_at) < trigger_time
        ][:6]

        explanation = self._explain(
            scenario_name=scenario["name"],
            trigger=trigger,
            leading=leading,
            trigger_summary=trigger_summary,
        )

        eligible.sort(key=lambda row: self._dt(row["observed_at"]))
        return TelemetryAssessment(
            scenario_id=scenario_id,
            scenario_name=scenario["name"],
            trigger_observation_id=trigger_id,
            trigger_observed_at=trigger["observed_at"],
            analysis_window_start=eligible[0]["observed_at"],
            analysis_window_end=eligible[-1]["observed_at"],
            future_samples_excluded=excluded,
            metric_summaries=summaries,
            timeline=timeline,
            leading_signals=leading,
            trigger_metric_summary=trigger_summary,
            temporal_explanation=explanation,
        )

    @staticmethod
    def _event(row: dict, event_type: str, threshold: float) -> TimelineEvent:
        return TimelineEvent(
            observed_at=row["observed_at"],
            event_type=event_type,
            metric_id=row["metric_id"],
            metric_name=row["metric_name"],
            entity_id=row["entity_id"],
            value=float(row["value"]),
            threshold=threshold,
            unit=row["unit"],
            source_system=row["source_system"],
            trust_level=row["trust_level"],
        )

    @staticmethod
    def _trend(values: list[float]) -> str:
        if len(values) < 2:
            return "INSUFFICIENT_DATA"
        delta = values[-1] - values[0]
        scale = max(abs(values[0]), 1.0)
        relative = delta / scale
        if relative >= 0.20:
            return "RISING"
        if relative <= -0.20:
            return "FALLING"
        return "STABLE"

    @staticmethod
    def _status(value: float, metric: dict) -> str:
        if value >= float(metric["critical_threshold"]):
            return "CRITICAL"
        if value >= float(metric["warning_threshold"]):
            return "HIGH"
        return "NORMAL"

    @staticmethod
    def _explain(
        *,
        scenario_name: str,
        trigger: dict,
        leading: list[TimelineEvent],
        trigger_summary: MetricSummary,
    ) -> str:
        if leading:
            lead_text = "; ".join(
                f"{event.metric_name} {event.event_type.lower().replace('_', ' ')} "
                f"at {event.observed_at}"
                for event in leading[:4]
            )
        else:
            lead_text = "No threshold-crossing leading signals were identified"

        return (
            f"For {scenario_name}, the evidence window ended at the trigger time "
            f"{trigger['observed_at']} to prevent future-data leakage. "
            f"{lead_text}. The trigger metric {trigger_summary.metric_name} "
            f"reached {trigger_summary.latest_value:g} "
            f"{trigger_summary.unit} against a critical threshold of "
            f"{trigger_summary.critical_threshold:g}. "
            f"This establishes temporal sequence and correlation, not causation."
        )

    @staticmethod
    def to_dict(assessment: TelemetryAssessment) -> dict:
        return asdict(assessment)
