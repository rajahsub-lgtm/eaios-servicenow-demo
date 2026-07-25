from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json

from operational_confidence_engine import (
    OperationalConfidenceAssessment,
    OperationalConfidenceEngine,
)
from skill_resolver import AgentSelection, SkillResolver


@dataclass(frozen=True)
class AdaptivePlan:
    scenario_id: str
    scenario_name: str
    orchestration_mode: str
    plan_name: str
    confidence_score: float
    confidence_level: str
    confidence_trend: str
    drift_status: str
    selected_known_error_id: str | None
    required_skills: list[str]
    selected_agents: list[AgentSelection]
    reasoning_agent_count: int
    uncovered_skills: list[str]
    reassessment_required: bool
    reassess_after_skills: list[str]
    expansion_mode: str | None
    decision_reasons: list[str]
    hard_flags: list[str]


class AdaptivePlanner:
    """Select a plan from confidence data and resolve skills through registry."""

    def __init__(
        self,
        confidence_engine: OperationalConfidenceEngine,
        skill_resolver: SkillResolver,
        orchestration_policy_file: str | Path,
    ) -> None:
        self.confidence_engine = confidence_engine
        self.skill_resolver = skill_resolver
        with open(orchestration_policy_file, encoding="utf-8") as f:
            self.policy = json.load(f)
        self.modes = sorted(
            self.policy["modes"],
            key=lambda row: int(row.get("priority", 0)),
            reverse=True,
        )

    def _supplemental_skills(self, scenario_id: str) -> list[str]:
        """Scenario-declared skills added to whichever mode is selected.

        Scoping the skill to the scenario keeps it out of every other
        scenario's plan, so existing mode definitions and their agent counts
        are unaffected.
        """
        scenario = self.confidence_engine.scenario_by_id.get(scenario_id, {})
        return list(scenario.get("supplemental_skills", []))

    def _required_skills(self, mode: dict, scenario_id: str) -> list[str]:
        """Base mode skills plus any the scenario supplements, in usable order.

        Supplemental skills gather evidence, so they are scheduled before the
        earliest reassessment that could act on it. Appending them at the end
        would let the plan be revised while the very evidence the scenario
        added was still outstanding.
        """
        skills = list(mode["required_skills"])
        supplemental = [
            skill
            for skill in self._supplemental_skills(scenario_id)
            if skill not in skills
        ]
        if not supplemental:
            return skills

        hooks = [
            skills.index(skill)
            for skill in mode.get("reassess_after_skills", [])
            if skill in skills
        ]
        if not hooks:
            return skills + supplemental
        cut = min(hooks)
        return skills[:cut] + supplemental + skills[cut:]

    def plan(
        self,
        scenario_id: str,
        *,
        as_of: str | None = None,
    ) -> AdaptivePlan:
        confidence = self.confidence_engine.assess(
            scenario_id,
            as_of=as_of,
        )
        mode, reasons = self._select_mode(confidence)
        required_skills = self._required_skills(mode, confidence.scenario_id)
        resolution = self.skill_resolver.resolve(required_skills)

        return AdaptivePlan(
            scenario_id=confidence.scenario_id,
            scenario_name=confidence.scenario_name,
            orchestration_mode=mode["mode_id"],
            plan_name=mode["name"],
            confidence_score=confidence.confidence_score,
            confidence_level=confidence.confidence_level,
            confidence_trend=confidence.confidence_trend,
            drift_status=confidence.drift_status,
            selected_known_error_id=confidence.selected_known_error_id,
            required_skills=list(required_skills),
            selected_agents=resolution.selected_agents,
            reasoning_agent_count=len(resolution.selected_agents),
            uncovered_skills=resolution.uncovered_skills,
            reassessment_required=bool(mode.get("reassess_after_skills")),
            reassess_after_skills=list(mode.get("reassess_after_skills", [])),
            expansion_mode=mode.get("expansion_mode"),
            decision_reasons=reasons,
            hard_flags=confidence.hard_flags,
        )

    def plan_from_confidence(
        self,
        confidence: OperationalConfidenceAssessment,
    ) -> AdaptivePlan:
        mode, reasons = self._select_mode(confidence)
        required_skills = self._required_skills(mode, confidence.scenario_id)
        resolution = self.skill_resolver.resolve(required_skills)
        return AdaptivePlan(
            scenario_id=confidence.scenario_id,
            scenario_name=confidence.scenario_name,
            orchestration_mode=mode["mode_id"],
            plan_name=mode["name"],
            confidence_score=confidence.confidence_score,
            confidence_level=confidence.confidence_level,
            confidence_trend=confidence.confidence_trend,
            drift_status=confidence.drift_status,
            selected_known_error_id=confidence.selected_known_error_id,
            required_skills=list(required_skills),
            selected_agents=resolution.selected_agents,
            reasoning_agent_count=len(resolution.selected_agents),
            uncovered_skills=resolution.uncovered_skills,
            reassessment_required=bool(mode.get("reassess_after_skills")),
            reassess_after_skills=list(mode.get("reassess_after_skills", [])),
            expansion_mode=mode.get("expansion_mode"),
            decision_reasons=reasons,
            hard_flags=confidence.hard_flags,
        )

    def _select_mode(
        self,
        confidence: OperationalConfidenceAssessment,
    ) -> tuple[dict, list[str]]:
        for mode in self.modes:
            conditions = mode.get("entry_conditions", {})
            if not conditions:
                return mode, [
                    "DEFAULT_OR_CONSERVATIVE_MODE",
                    f"CONFIDENCE_{confidence.confidence_level}",
                    f"DRIFT_{confidence.drift_status}",
                ]

            failures = self._condition_failures(confidence, conditions)
            if not failures:
                return mode, [
                    f"CONFIDENCE_{confidence.confidence_level}",
                    f"DRIFT_{confidence.drift_status}",
                    "EVIDENCE_COVERAGE_SUFFICIENT",
                    "CONTRADICTION_WITHIN_TOLERANCE",
                    "CANDIDATE_MARGIN_SUFFICIENT",
                    "NO_DISALLOWED_HARD_FLAGS",
                ]

        default_id = self.policy["default_mode"]
        default_mode = next(
            mode for mode in self.modes
            if mode["mode_id"] == default_id
        )
        return default_mode, ["DEFAULT_POLICY_FALLBACK"]

    @staticmethod
    def _condition_failures(
        confidence: OperationalConfidenceAssessment,
        conditions: dict,
    ) -> list[str]:
        failures = []

        levels = conditions.get("confidence_levels")
        if levels and confidence.confidence_level not in levels:
            failures.append("CONFIDENCE_LEVEL")

        drift = conditions.get("allowed_drift_statuses")
        if drift and confidence.drift_status not in drift:
            failures.append("DRIFT_STATUS")

        if confidence.evidence_coverage < float(
            conditions.get("minimum_evidence_coverage", 0.0)
        ):
            failures.append("EVIDENCE_COVERAGE")

        if confidence.contradiction_level > float(
            conditions.get("maximum_contradiction_level", 1.0)
        ):
            failures.append("CONTRADICTION_LEVEL")

        if confidence.candidate_margin < float(
            conditions.get("minimum_candidate_margin", 0.0)
        ):
            failures.append("CANDIDATE_MARGIN")

        disallowed = set(conditions.get("disallowed_hard_flags", []))
        if disallowed & set(confidence.hard_flags):
            failures.append("HARD_FLAGS")

        return failures

    @staticmethod
    def to_dict(result: AdaptivePlan) -> dict:
        return asdict(result)
