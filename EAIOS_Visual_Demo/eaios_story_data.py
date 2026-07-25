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
    scenarios: Path

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
            scenarios=base / "json" / "scenarios.json",
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
    scenario_metadata: dict[str, dict[str, Any]]

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

        scenario_metadata: dict[str, dict[str, Any]] = {}
        if paths.scenarios.exists():
            scenario_metadata = {
                row["scenario_id"]: row
                for row in json.loads(paths.scenarios.read_text(encoding="utf-8"))
            }

        return cls(
            paths=paths,
            bundle=bundle,
            execution_events=pd.read_csv(paths.execution_events),
            plan_revisions=pd.read_csv(paths.plan_revisions),
            automation_readiness=pd.read_csv(paths.automation_readiness),
            confidence_maturation=pd.read_csv(paths.confidence_maturation),
            visual_config=visual_config,
            scenario_metadata=scenario_metadata,
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

    def readiness_confidence_threshold(self) -> float:
        """The confidence bar readiness actually applies.

        Read from policy so the chart and the evaluator cannot disagree after
        the threshold is tuned.
        """
        path = self.paths.base_dir / "config" / "automation_readiness_policy.json"
        if not path.exists():
            return 0.9
        policy = json.loads(path.read_text(encoding="utf-8"))
        return float(policy["thresholds"]["minimum_confidence_score"])

    def scenario_identity(self, scenario_id: str) -> dict[str, str]:
        """Declared identity for a scenario, with a derived last resort.

        Identity is what the scenario is about. Expansion and contraction
        describe how a particular run behaved, which is a property of the
        execution and cannot stand in for the story being told: two scenarios
        can contract for entirely different reasons.
        """
        row = self.scenario_metadata.get(scenario_id, {})
        fallback = format_identifier(
            scenario_id.removeprefix("SCN-").replace("-", " ")
        )
        return {
            "display_name": row.get("display_name") or row.get("name") or fallback,
            "short_label": row.get("short_label") or fallback,
            "scenario_category": row.get("scenario_category", ""),
        }

    def _friendly_scenario_label(self, assessment: dict[str, Any]) -> str:
        return self.scenario_identity(assessment.get("scenario_id", ""))["display_name"]

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
        # Cancelled skills were queued by a previous plan and never executed.
        # They accumulate across revisions, so collect every transition.
        cancelled: list[str] = []
        for transition in transitions:
            for skill in transition.get("cancelled_skills", []) or []:
                if skill not in cancelled:
                    cancelled.append(skill)
        executed = list(assessment.get("completed_skills", []))
        cancelled = [skill for skill in cancelled if skill not in executed]

        return {
            "initial": initial,
            "final": final,
            "preserved": preserved,
            "added": added,
            "removed": removed,
            "cancelled": cancelled,
            "directions": [
                transition.get("direction", "EXPANSION")
                for transition in transitions
            ],
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

    def comparison_metrics(self, correlation_id: str) -> dict[str, Any]:
        """One scenario's comparable figures, in a fixed order.

        The same metrics are reported for every scenario so the two columns
        can be read against each other without the meaning shifting between
        them.
        """
        assessment = self.get_assessment(correlation_id)
        preview = self.get_servicenow_preview(correlation_id)
        conceptual = preview.get("conceptual_values", {})
        counts = self.conflict_counts(correlation_id)
        readiness = assessment.get("automation_readiness", {})

        return {
            "Initial confidence": (
                f"{assessment['initial_confidence_score']:.3f} "
                f"{assessment['initial_confidence_level']}"
            ),
            "Final confidence": (
                f"{assessment['final_confidence_score']:.3f} "
                f"{assessment['final_confidence_level']}"
            ),
            "Initial plan width": assessment.get(
                "initial_plan_agent_count", assessment["initial_agent_count"]
            ),
            "Peak plan width": assessment.get(
                "peak_plan_agent_count", assessment["initial_agent_count"]
            ),
            "Final plan width": assessment.get(
                "final_plan_agent_count", assessment["final_agent_count"]
            ),
            "Unique agents contributing": assessment.get(
                "unique_agents_executed", assessment["final_agent_count"]
            ),
            "Readiness state": readiness.get("status", ""),
            "Approval status": str(
                conceptual.get("Approval state", assessment.get("approval_state", ""))
            ).replace("AWAITING_APPROVAL", "REQUESTED"),
            "Active conflicts": counts["active"],
            "Resolved conflicts": counts["resolved"],
        }

    def compare(self, baseline_id: str, comparison_id: str) -> pd.DataFrame:
        baseline = self.comparison_metrics(baseline_id)
        comparison = self.comparison_metrics(comparison_id)
        labels = self.assessment_labels()
        return pd.DataFrame(
            [
                {
                    "Metric": metric,
                    labels.get(baseline_id, baseline_id): baseline[metric],
                    labels.get(comparison_id, comparison_id): comparison[metric],
                }
                for metric in baseline
            ]
        )

    def vendor_health(self, correlation_id: str) -> dict[str, Any]:
        """External service-health evidence, when the scenario gathered any."""
        assessment = self.get_assessment(correlation_id)
        return dict(
            assessment.get("skill_outputs", {}).get("external_service_health", {})
        )

    def vendor_findings(self, correlation_id: str) -> pd.DataFrame:
        findings = self.vendor_health(correlation_id).get("findings", []) or []
        rows = [
            {
                "Advisory": item.get("advisory_id", ""),
                "Vendor": item.get("vendor", ""),
                "Service": item.get("service", ""),
                "Reported": item.get("status", ""),
                "Authority": item.get("source_authority", ""),
                "Age (min)": item.get("freshness_minutes", ""),
                "Usable": "Yes" if item.get("eliminates_external_hypothesis") else "No",
                "Why not": ", ".join(
                    format_identifier(reason)
                    for reason in item.get("disqualification_reasons", []) or []
                ),
            }
            for item in findings
        ]
        return pd.DataFrame(rows)

    def shared_dependency_paths(self, correlation_id: str) -> list[dict[str, Any]]:
        """Graph routes that converge, as recorded by the semantic context skill."""
        assessment = self.get_assessment(correlation_id)
        context = assessment.get("skill_outputs", {}).get("semantic_context", {})
        return list(context.get("authoritative_paths", []) or [])

    CONTRADICTION_FLAG = "CREDIBLE_KNOWLEDGE_CONTRADICTION"

    def _contradiction_events(self, correlation_id: str) -> dict[str, Any]:
        """Where the contradiction was raised and, if ever, where it was retired.

        Both are read from the reassessment record rather than stored on the
        conflict, so the retrieval output stays exactly as it was written.
        """
        assessment = self.get_assessment(correlation_id)
        reassessments = (
            assessment.get("skill_outputs", {}).get("confidence_reassessments")
            or {}
        )
        detected: tuple[str, dict[str, Any]] | None = None
        resolved: tuple[str, dict[str, Any]] | None = None
        for skill_id, record in reassessments.items():
            signals = record.get("runtime_signal_types") or []
            cleared = record.get("resolved_hard_flags") or []
            if detected is None and self.CONTRADICTION_FLAG in signals:
                detected = (skill_id, record)
            if resolved is None and self.CONTRADICTION_FLAG in cleared:
                resolved = (skill_id, record)
        return {"detected": detected, "resolved": resolved}

    def conflict_adjudications(self, correlation_id: str) -> list[dict[str, Any]]:
        """Each material conflict with its current adjudication.

        The conflict record itself is never rewritten. A conflict that was
        material when retrieved stays material when retrieved; if later evidence
        retired it, that is a separate governed decision recorded alongside,
        with the skill and signals that carried it.
        """
        conflicts = self.material_conflicts(correlation_id)
        if not conflicts:
            return []

        events = self._contradiction_events(correlation_id)
        detected = events["detected"]
        resolved = events["resolved"]

        rows: list[dict[str, Any]] = []
        for conflict in conflicts:
            row: dict[str, Any] = {
                "source_id": conflict.get("source_id", ""),
                "title": conflict.get("title", ""),
                "original_disposition": conflict.get("governance_decision", ""),
                "original_status": "MATERIAL_AT_RETRIEVAL",
                "detected_after_skill": detected[0] if detected else "",
                "adjudication": "RESOLVED" if resolved else "ACTIVE",
                "governed_event": (
                    f"{self.CONTRADICTION_FLAG} resolved"
                    if resolved
                    else f"{self.CONTRADICTION_FLAG} outstanding"
                ),
            }
            if resolved:
                skill_id, record = resolved
                row.update(
                    {
                        "resolved_after_skill": skill_id,
                        "resolving_signals": list(
                            record.get("runtime_signal_types") or []
                        ),
                        "confidence_before": record.get("initial_confidence_score"),
                        "confidence_after": record.get("updated_confidence_score"),
                        "level_before": record.get("initial_confidence_level", ""),
                        "level_after": record.get("updated_confidence_level", ""),
                        "resolved_by": (
                            f"{format_identifier(skill_id)} retired the alternative "
                            "explanation"
                        ),
                    }
                )
            rows.append(row)
        return rows

    def conflict_counts(self, correlation_id: str) -> dict[str, int]:
        rows = self.conflict_adjudications(correlation_id)
        resolved = sum(1 for row in rows if row["adjudication"] == "RESOLVED")
        return {
            "active": len(rows) - resolved,
            "resolved": resolved,
            "total": len(rows),
        }

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
