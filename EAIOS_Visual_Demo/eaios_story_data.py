from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote
import json

import pandas as pd


class StoryDataError(RuntimeError):
    """Raised when the visual-story inputs are missing or inconsistent."""


@dataclass(frozen=True)
class StoryPaths:
    base_dir: Path
    bundle: Path
    execution_events: Path
    plan_revisions: Path
    automation_readiness: Path
    confidence_maturation: Path
    visual_config: Path

    @classmethod
    def from_base_dir(cls, base_dir: str | Path) -> "StoryPaths":
        base = Path(base_dir).resolve()
        outputs = base / "outputs"
        return cls(
            base_dir=base,
            bundle=outputs / "servicenow_story_bundle.json",
            execution_events=outputs / "servicenow_execution_events.csv",
            plan_revisions=outputs / "servicenow_plan_revisions.csv",
            automation_readiness=outputs / "servicenow_automation_readiness.csv",
            confidence_maturation=outputs / "servicenow_confidence_maturation.csv",
            visual_config=base / "config" / "visual_demo.json",
        )


@dataclass
class StoryRepository:
    paths: StoryPaths
    bundle: dict[str, Any]
    execution_events: pd.DataFrame
    plan_revisions: pd.DataFrame
    automation_readiness: pd.DataFrame
    confidence_maturation: pd.DataFrame
    visual_config: dict[str, Any]

    @classmethod
    def load(cls, base_dir: str | Path) -> "StoryRepository":
        paths = StoryPaths.from_base_dir(base_dir)
        required = [
            paths.bundle,
            paths.execution_events,
            paths.plan_revisions,
            paths.automation_readiness,
            paths.confidence_maturation,
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise StoryDataError(
                "Missing visual-story input files: " + ", ".join(missing)
            )

        bundle = json.loads(paths.bundle.read_text(encoding="utf-8"))
        assessments = bundle.get("assessments")
        if not isinstance(assessments, list) or not assessments:
            raise StoryDataError("Story bundle contains no assessments.")

        visual_config: dict[str, Any] = {}
        if paths.visual_config.exists():
            visual_config = json.loads(paths.visual_config.read_text(encoding="utf-8"))

        return cls(
            paths=paths,
            bundle=bundle,
            execution_events=pd.read_csv(paths.execution_events),
            plan_revisions=pd.read_csv(paths.plan_revisions),
            automation_readiness=pd.read_csv(paths.automation_readiness),
            confidence_maturation=pd.read_csv(paths.confidence_maturation),
            visual_config=visual_config,
        )

    @property
    def assessments(self) -> list[dict[str, Any]]:
        return list(self.bundle["assessments"])

    def assessment_labels(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for assessment in self.assessments:
            correlation_id = assessment["correlation_id"]
            labels[correlation_id] = self._friendly_scenario_label(assessment)
        return labels

    @staticmethod
    def _friendly_scenario_label(assessment: dict[str, Any]) -> str:
        if assessment.get("expanded_during_execution"):
            return "Contradictory knowledge — confidence erodes"
        return "Stable evidence — confidence remains high"

    def get_assessment(self, correlation_id: str) -> dict[str, Any]:
        for assessment in self.assessments:
            if assessment.get("correlation_id") == correlation_id:
                return assessment
        raise StoryDataError(f"Unknown assessment correlation ID: {correlation_id}")

    def get_servicenow_preview(self, correlation_id: str) -> dict[str, Any]:
        for preview in self.bundle.get("servicenow_previews", []):
            conceptual = preview.get("conceptual_values", {})
            if conceptual.get("Correlation ID") == correlation_id:
                return preview
        return {}

    def get_execution_events(self, correlation_id: str) -> pd.DataFrame:
        frame = self.execution_events[
            self.execution_events["correlation_id"] == correlation_id
        ].copy()
        if frame.empty:
            return frame
        frame["sequence"] = pd.to_numeric(frame["sequence"], errors="coerce")
        return frame.sort_values("sequence").reset_index(drop=True)

    def get_plan_revisions(self, correlation_id: str) -> pd.DataFrame:
        frame = self.plan_revisions[
            self.plan_revisions["correlation_id"] == correlation_id
        ].copy()
        if frame.empty:
            return frame
        frame["revision_number"] = pd.to_numeric(
            frame["revision_number"], errors="coerce"
        )
        return frame.sort_values("revision_number").reset_index(drop=True)

    def confidence_series(self, correlation_id: str) -> pd.DataFrame:
        assessment = self.get_assessment(correlation_id)
        events = self.get_execution_events(correlation_id)
        points: list[dict[str, Any]] = []

        for _, row in events.iterrows():
            value = pd.to_numeric(row.get("confidence_after"), errors="coerce")
            if pd.isna(value):
                continue
            event_type = str(row.get("event_type") or "CONFIDENCE_UPDATED")
            summary = str(row.get("summary") or "")
            points.append(
                {
                    "sequence": int(row["sequence"]),
                    "event": event_type.replace("_", " ").title(),
                    "confidence": float(value),
                    "level": str(row.get("confidence_level_after") or ""),
                    "summary": summary,
                }
            )

        if not points:
            points = [
                {
                    "sequence": 0,
                    "event": "Initial confidence",
                    "confidence": float(assessment["initial_confidence_score"]),
                    "level": assessment["initial_confidence_level"],
                    "summary": "Initial confidence selected the first plan.",
                },
                {
                    "sequence": 1,
                    "event": "Final confidence",
                    "confidence": float(assessment["final_confidence_score"]),
                    "level": assessment["final_confidence_level"],
                    "summary": "Final confidence after governed execution.",
                },
            ]

        # Ensure the final point matches the authoritative assessment summary.
        final_score = float(assessment["final_confidence_score"])
        if abs(float(points[-1]["confidence"]) - final_score) > 1e-9:
            points.append(
                {
                    "sequence": int(points[-1]["sequence"]) + 1,
                    "event": "Final confidence",
                    "confidence": final_score,
                    "level": assessment["final_confidence_level"],
                    "summary": assessment.get("recommendation", {}).get(
                        "reasoning_summary", "Final governed confidence."
                    ),
                }
            )

        return pd.DataFrame(points)

    def plan_delta(self, correlation_id: str) -> dict[str, Any]:
        assessment = self.get_assessment(correlation_id)
        initial = list(assessment.get("required_skills_initial", []))
        final = list(assessment.get("required_skills_final", []))
        transitions = assessment.get("plan_transitions", []) or []

        if transitions:
            latest = transitions[-1]
            preserved = list(latest.get("completed_skills_retained", []))
            added = list(latest.get("added_skills", []))
        else:
            preserved = [skill for skill in initial if skill in final]
            added = [skill for skill in final if skill not in initial]

        removed = [
            skill for skill in initial
            if skill not in preserved and skill not in final
        ]
        return {
            "initial": initial,
            "final": final,
            "preserved": preserved,
            "added": added,
            "removed": removed,
        }

    def readiness_criteria(self, correlation_id: str) -> pd.DataFrame:
        assessment = self.get_assessment(correlation_id)
        readiness = assessment.get("automation_readiness", {})
        rows = []
        for criterion in readiness.get("criteria", []):
            rows.append(
                {
                    "status": "PASS" if criterion.get("passed") else "BLOCKED",
                    "criterion": criterion.get("label", criterion.get("criterion_id")),
                    "actual": self._display_value(criterion.get("actual")),
                    "required": self._display_value(criterion.get("required")),
                    "explanation": criterion.get("explanation", ""),
                    "criterion_id": criterion.get("criterion_id", ""),
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _display_value(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.3f}".rstrip("0").rstrip(".")
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        if isinstance(value, bool):
            return "Yes" if value else "No"
        return str(value)

    def knowledge_items(self, correlation_id: str) -> pd.DataFrame:
        assessment = self.get_assessment(correlation_id)
        retrieval = assessment.get("skill_outputs", {}).get(
            "governed_knowledge_retrieval", {}
        )
        rows: list[dict[str, Any]] = []
        for bucket, default_decision in (
            ("accepted_free_text", "ACCEPTED"),
            ("accepted_with_limitations", "ACCEPTED_WITH_LIMITATIONS"),
            ("rejected_candidates", "REJECTED"),
        ):
            for item in retrieval.get(bucket, []) or []:
                rows.append(
                    {
                        "source_id": item.get("source_id", ""),
                        "title": item.get("title", ""),
                        "source_type": item.get("source_type", ""),
                        "trust": item.get("trust_level", ""),
                        "decision": item.get("governance_decision", default_decision),
                        "material_contradiction": bool(
                            item.get("material_contradiction", False)
                        ),
                        "corroboration_count": item.get("corroboration_count", 0),
                        "enterprise_approved": item.get("enterprise_approved"),
                        "reasons": ", ".join(
                            item.get("limitation_reasons", [])
                            or item.get("rejection_reasons", [])
                            or []
                        ),
                        "score": item.get("score"),
                    }
                )
        return pd.DataFrame(rows)

    def material_conflicts(self, correlation_id: str) -> list[dict[str, Any]]:
        assessment = self.get_assessment(correlation_id)
        retrieval = assessment.get("skill_outputs", {}).get(
            "governed_knowledge_retrieval", {}
        )
        conflicts: list[dict[str, Any]] = []
        for item in retrieval.get("accepted_with_limitations", []) or []:
            if item.get("material_contradiction"):
                conflicts.append(item)
        return conflicts

    def servicenow_record_metadata(self, correlation_id: str) -> dict[str, Any]:
        records = self.visual_config.get("records", {})
        return dict(records.get(correlation_id, {}))

    def servicenow_record_url(self, correlation_id: str) -> str | None:
        instance_url = str(self.visual_config.get("instance_url", "")).rstrip("/")
        table = self.visual_config.get(
            "assessment_table", "u_eaios_operational_assessment"
        )
        if not instance_url:
            return None

        metadata = self.servicenow_record_metadata(correlation_id)
        sys_id = metadata.get("sys_id")
        view = self.visual_config.get("assessment_view", "eaios_demo")
        if sys_id:
            target = (
                f"{table}.do?sys_id={quote(str(sys_id))}"
                f"&sysparm_view={quote(str(view))}"
            )
        else:
            query = quote(f"u_correlation_id={correlation_id}")
            target = f"{table}_list.do?sysparm_query={query}"
        return f"{instance_url}/now/nav/ui/classic/params/target/{quote(target, safe='')}"


def format_identifier(identifier: str) -> str:
    return identifier.replace("_", " ").strip().title()
