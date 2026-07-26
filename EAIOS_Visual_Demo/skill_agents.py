from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

from evidence_fusion_agent import EvidenceFusionAgent
from graph_context_agent import GraphContextAgent
from knowledge_retrieval_agent import KnowledgeRetrievalAgent
from operational_confidence_engine import OperationalConfidenceAssessment
from runtime_evidence import RuntimeEvidenceProbe, RuntimeEvidenceSignal
from telemetry_agent import TelemetryAnalysisAgent


@dataclass(frozen=True)
class SkillExecutionResult:
    skill_id: str
    agent_id: str
    summary: str
    output: dict
    runtime_signals: list[RuntimeEvidenceSignal]


class DueDiligenceValidationAgent:
    def __init__(self, json_dir: str | Path) -> None:
        self.json_dir = Path(json_dir)
        self.probe = RuntimeEvidenceProbe(self.json_dir)

    def execute(
        self,
        *,
        scenario_id: str,
        confidence: OperationalConfidenceAssessment,
        graph_context: dict,
    ) -> SkillExecutionResult:
        relevant_entities = set(
            graph_context.get("authoritative_entity_ids", [])
        )
        signals = self.probe.discover(
            scenario_id=scenario_id,
            entity_ids=relevant_entities,
            after_skill="due_diligence_validation",
        )
        summary = (
            f"Validated {len(relevant_entities)} governed context entities; "
            f"discovered {len(signals)} new runtime signal(s)."
        )
        return SkillExecutionResult(
            skill_id="due_diligence_validation",
            agent_id="due_diligence_agent",
            summary=summary,
            output={
                "initial_confidence_score": confidence.confidence_score,
                "initial_confidence_level": confidence.confidence_level,
                "validated_entity_ids": sorted(relevant_entities),
                "runtime_signal_types": [
                    signal.signal_type for signal in signals
                ],
                "runtime_signals": [asdict(signal) for signal in signals],
                "material_knowledge_conflict_ids": [
                    signal.knowledge_source_id
                    for signal in signals
                    if signal.signal_type == "CREDIBLE_KNOWLEDGE_CONTRADICTION"
                    and signal.knowledge_source_id
                ],
                "due_diligence_passed": not signals,
            },
            runtime_signals=signals,
        )


class ChangeDependencyInvestigationAgent:
    def __init__(self, json_dir: str | Path) -> None:
        self.json_dir = Path(json_dir)
        self.changes = self._load("changes.json")
        self.probe = RuntimeEvidenceProbe(self.json_dir)

    def _load(self, filename: str) -> list[dict]:
        with open(self.json_dir / filename, encoding="utf-8") as f:
            return json.load(f)

    def execute(
        self,
        *,
        scenario_id: str,
        graph_context: dict,
        runtime_signals: list[RuntimeEvidenceSignal],
    ) -> SkillExecutionResult:
        relevant = set(graph_context.get("authoritative_entity_ids", []))
        changes = [
            row for row in self.changes
            if row.get("entity_id") in relevant
        ]
        hypotheses = [
            {
                "hypothesis_id": row["change_id"],
                "type": "CHANGE_CORRELATION",
                "status": "UNCONFIRMED",
                "entity_id": row["entity_id"],
                "risk": row["risk"],
                "implemented_at": row["implemented_at"],
            }
            for row in changes
        ]
        for signal in runtime_signals:
            hypotheses.append(
                {
                    "hypothesis_id": signal.signal_id,
                    "type": signal.signal_type,
                    "status": "RUNTIME_EVIDENCE_REQUIRES_VALIDATION",
                    "entity_id": signal.entity_id,
                    "risk": "UNKNOWN",
                    "implemented_at": "",
                }
            )
        # Deeper investigation can also retire hypotheses. Signals discovered
        # here may resolve earlier hard flags and narrow the plan again.
        discovered = self.probe.discover(
            scenario_id=scenario_id,
            entity_ids=relevant,
            after_skill="change_dependency_investigation",
        )
        return SkillExecutionResult(
            skill_id="change_dependency_investigation",
            agent_id="change_dependency_agent",
            summary=(
                f"Retained {len(hypotheses)} change/dependency hypothesis "
                f"record(s) without promoting correlation to causation; "
                f"discovered {len(discovered)} resolving signal(s)."
            ),
            output={
                "hypotheses": hypotheses,
                "causal_status": "UNCONFIRMED",
                "resolving_signal_types": [
                    signal.signal_type for signal in discovered
                ],
            },
            runtime_signals=discovered,
        )


class AdaptiveRecommendationAgent:
    def __init__(self, json_dir: str | Path) -> None:
        self.fusion = EvidenceFusionAgent(json_dir)

    def execute(
        self,
        *,
        scenario_id: str,
        orchestration_mode: str,
        plan_name: str,
        confidence: OperationalConfidenceAssessment,
        completed_outputs: dict[str, dict],
    ) -> SkillExecutionResult:
        # Vendor findings are another agent's governed output, not a re-read of
        # the source. Fusion weighs what the vendor agent actually established,
        # including its freshness and authority judgements.
        fusion = self.fusion.analyze(
            scenario_id,
            vendor_health=completed_outputs.get("external_service_health"),
        )

        retrieval = completed_outputs.get("governed_knowledge_retrieval", {})
        limited = retrieval.get("accepted_with_limitations", [])
        material_conflicts = [
            row for row in limited
            if row.get("material_contradiction")
        ]
        material_conflict_ids = [
            row.get("source_id") for row in material_conflicts
            if row.get("source_id")
        ]
        alternative_ids = sorted({
            row.get("alternative_hypothesis_id")
            for row in material_conflicts
            if row.get("alternative_hypothesis_id")
        })

        if fusion.leading_hypothesis.hypothesis_type == "NO_DIAGNOSIS":
            # There is no hypothesis to caveat. Phrasing this like a normal
            # recommendation would advise restarting something the run cannot
            # explain, which is precisely the borrowed remedy it must refuse.
            action = fusion.recommended_action
        elif orchestration_mode == "ACCELERATED_VALIDATION":
            action = fusion.recommended_action
        elif material_conflict_ids:
            action = (
                f"Treat {fusion.leading_hypothesis.title} as a leading "
                f"hypothesis rather than confirmed root cause. Newly retrieved "
                f"knowledge ({', '.join(material_conflict_ids)}) presents a "
                f"credible material contradiction but is not independently "
                f"corroborated or enterprise approved. Continue the full "
                f"investigation across detailed telemetry, recent changes, "
                f"dependency health, and authoritative records before any "
                f"connector restart. Obtain human approval before remediation."
            )
        else:
            action = (
                f"Treat {fusion.leading_hypothesis.title} as a leading "
                f"hypothesis rather than confirmed root cause. Continue the "
                f"full investigation using completed telemetry, retrieval, "
                f"change/dependency, and graph evidence. Obtain human approval "
                f"before rollback, restart, scaling, or traffic changes."
            )

        uncertainty = set(fusion.uncertainty_factors) | set(confidence.hard_flags)
        if material_conflict_ids:
            uncertainty.add("UNRESOLVED_MATERIAL_KNOWLEDGE_CONTRADICTION")

        reasoning_summary = (
            f"Adaptive plan {orchestration_mode} selected from current "
            f"operational confidence. Existing evidence fusion identified "
            f"{fusion.leading_hypothesis.hypothesis_id}; plan strategy "
            f"remains controlled by the adaptive planner."
        )
        if material_conflict_ids:
            reasoning_summary += (
                f" Credible but limited knowledge {material_conflict_ids} "
                f"challenged the leading hypothesis, reduced confidence, and "
                f"expanded the required governed skills without promoting the "
                f"new source to confirmed truth."
            )

        return SkillExecutionResult(
            skill_id=(
                "governed_recommendation"
                if orchestration_mode == "ACCELERATED_VALIDATION"
                else "evidence_fusion_recommendation"
            ),
            agent_id=(
                "recommendation_governance_agent"
                if orchestration_mode == "ACCELERATED_VALIDATION"
                else "evidence_fusion_agent"
            ),
            summary=(
                f"{plan_name}; {confidence.confidence_level} confidence "
                f"{confidence.confidence_score:.3f}; "
                f"hypothesis {fusion.leading_hypothesis.hypothesis_id}."
            ),
            output={
                "leading_hypothesis_id": fusion.leading_hypothesis.hypothesis_id,
                "leading_hypothesis_title": fusion.leading_hypothesis.title,
                "alternative_hypothesis_ids": sorted(
                    set(
                        item.hypothesis_id
                        for item in fusion.alternative_hypotheses
                    )
                    | set(alternative_ids)
                ),
                # Retired candidates are reported with their reason. A record
                # that shows only what survived cannot be audited.
                "retired_hypotheses": [
                    {
                        "hypothesis_id": item.hypothesis_id,
                        "title": item.title,
                        "score": item.score,
                        "rejection_reason": item.rejection_reason,
                        "contradicting_evidence_ids": list(
                            item.contradicting_evidence_ids
                        ),
                    }
                    for item in fusion.alternative_hypotheses
                    if item.status == "REJECTED"
                ],
                # Every candidate considered, with its score and disposition.
                # Reporting only the winner hides the reasoning that chose it.
                "hypotheses": [
                    {
                        "hypothesis_id": item.hypothesis_id,
                        "hypothesis_type": item.hypothesis_type,
                        "title": item.title,
                        "score": item.score,
                        "confidence_level": item.confidence_level,
                        "status": status,
                        "supporting_evidence_ids": list(item.supporting_evidence_ids),
                        "contradicting_evidence_ids": list(
                            item.contradicting_evidence_ids
                        ),
                        "rejection_reason": item.rejection_reason,
                        "uncertainty_factors": list(item.uncertainty_factors),
                        "historical_success_rate": item.historical_success_rate,
                    }
                    for item, status in (
                        [(fusion.leading_hypothesis, "LEADING")]
                        + [(alt, alt.status) for alt in fusion.alternative_hypotheses]
                    )
                ],
                # What each source contributed, weighted, with provenance.
                # This is the collective part of collective intelligence.
                "evidence_ledger": [
                    {
                        "evidence_id": item.evidence_id,
                        "evidence_type": item.evidence_type,
                        "evidence_class": item.evidence_class,
                        "role": item.role,
                        "reliability": item.reliability,
                        "contribution": item.contribution,
                        "rationale": item.rationale,
                        "provenance": item.provenance,
                    }
                    for item in fusion.evidence_ledger
                ],
                "rejected_evidence_count": len(fusion.rejected_evidence_ids),
                "reasoning_summary": fusion.reasoning_summary,
                "selected_strategy": plan_name,
                "confidence_level": confidence.confidence_level,
                "confidence_score": confidence.confidence_score,
                "safety_status": "REQUIRES_HUMAN_APPROVAL",
                "human_approval_required": True,
                "recommended_action": action,
                "validation_steps": fusion.validation_steps,
                "uncertainty_factors": sorted(uncertainty),
                "guardrail_reasons": fusion.guardrail_reasons,
                "material_conflict_source_ids": material_conflict_ids,
                "knowledge_disposition": (
                    "ACCEPTED_WITH_LIMITATIONS"
                    if material_conflict_ids
                    else "NO_MATERIAL_CONFLICT"
                ),
                "unresolved_material_conflict": bool(material_conflict_ids),
                "reasoning_summary": reasoning_summary,
            },
            runtime_signals=[],
        )

