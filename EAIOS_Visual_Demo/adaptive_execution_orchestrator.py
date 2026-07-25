from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
import json
import uuid

from adaptive_planner import AdaptivePlan, AdaptivePlanner
from automation_readiness import AutomationReadinessEvaluator
from graph_context_agent import GraphContextAgent
from knowledge_retrieval_agent import KnowledgeRetrievalAgent
from operational_confidence_engine import (
    OperationalConfidenceAssessment,
    OperationalConfidenceEngine,
)
from policy_layer import (
    A2AEnforcementPoint,
    DataAccessEnforcementPoint,
    MCPEnforcementPoint,
    PolicyDecision,
    PolicyDecisionPoint,
    PolicyRequest,
)
from runtime_confidence_reassessment import (
    ReassessmentResult,
    RuntimeConfidenceReassessor,
)
from runtime_evidence import RuntimeEvidenceSignal
from skill_agents import (
    AdaptiveRecommendationAgent,
    ChangeDependencyInvestigationAgent,
    DueDiligenceValidationAgent,
    SkillExecutionResult,
)
from skill_resolver import AgentSelection, SkillResolver
from telemetry_agent import TelemetryAnalysisAgent
from vendor_health_agent import VendorHealthAgent


UTC = timezone.utc


@dataclass(frozen=True)
class SkillExecutionTrace:
    sequence: int
    skill_id: str
    agent_id: str
    agent_name: str
    status: str
    started_at: str
    completed_at: str
    duration_ms: float
    summary: str
    policy_decision_ids: list[str]
    error: str | None


@dataclass(frozen=True)
class PlanTransition:
    from_mode: str
    to_mode: str
    direction: str
    triggered_after_skill: str
    reason: str
    completed_skills_retained: list[str]
    added_skills: list[str]
    cancelled_skills: list[str]


@dataclass(frozen=True)
class AdaptiveExecutionAssessment:
    execution_id: str
    correlation_id: str
    scenario_id: str
    scenario_name: str
    initial_plan_mode: str
    final_plan_mode: str
    initial_confidence_score: float
    final_confidence_score: float
    initial_confidence_level: str
    final_confidence_level: str
    drift_status: str
    expanded_during_execution: bool
    contracted_during_execution: bool
    plan_transitions: list[PlanTransition]
    required_skills_initial: list[str]
    required_skills_final: list[str]
    completed_skills: list[str]
    reasoning_agents_executed: list[str]
    reasoning_agent_execution_count: int
    # Legacy pair, meaning preserved: initial plan width, then unique agents
    # actually executed. Asymmetric, but frozen so V1 outputs do not move.
    initial_agent_count: int
    final_agent_count: int
    # Canonical metrics. Plan widths come from resolved plans; participation
    # comes from the execution trace. Never derive one from the other.
    initial_plan_agent_count: int
    peak_plan_agent_count: int
    final_plan_agent_count: int
    unique_agents_executed: int
    automation_readiness: dict
    recommendation: dict
    skill_outputs: dict[str, dict]
    execution_trace: list[SkillExecutionTrace]
    policy_decisions: list[PolicyDecision]
    policy_decision_counts: dict[str, int]
    safety_status: str
    approval_state: str
    generated_at: str


class AdaptiveExecutionOrchestrator:
    """Execute the selected skill plan and expand it when confidence erodes."""

    def __init__(
        self,
        root: str | Path,
        *,
        json_dir: str | Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.json_dir = Path(json_dir) if json_dir else self.root / "json"

        config = self.root / "config"
        self.confidence_engine = OperationalConfidenceEngine(
            self.json_dir,
            config / "confidence_policy.json",
        )
        self.skill_resolver = SkillResolver(
            config / "skill_catalog.json",
            config / "agent_registry.json",
        )
        self.planner = AdaptivePlanner(
            self.confidence_engine,
            self.skill_resolver,
            config / "orchestration_policies.json",
        )
        self.reassessor = RuntimeConfidenceReassessor(
            config / "runtime_signal_policy.json",
            config / "confidence_policy.json",
        )
        self.readiness_evaluator = AutomationReadinessEvaluator(
            config / "automation_readiness_policy.json"
        )

        self.policy_audit: list[PolicyDecision] = []
        self.pdp = PolicyDecisionPoint(
            config / "access_policies.json",
            config / "agent_registry.json",
            config / "skill_catalog.json",
        )
        self.a2a_pep = A2AEnforcementPoint(self.pdp, self.policy_audit)
        self.mcp_pep = MCPEnforcementPoint(self.pdp, self.policy_audit)
        self.data_pep = DataAccessEnforcementPoint(
            self.pdp, self.policy_audit
        )

        self.graph_agent = GraphContextAgent(self.json_dir)
        self.telemetry_agent = TelemetryAnalysisAgent(self.json_dir)
        self.retrieval_agent = KnowledgeRetrievalAgent(self.json_dir)
        self.due_diligence_agent = DueDiligenceValidationAgent(self.json_dir)
        self.change_agent = ChangeDependencyInvestigationAgent(self.json_dir)
        self.recommendation_agent = AdaptiveRecommendationAgent(self.json_dir)
        self.vendor_health_agent = VendorHealthAgent(
            self.json_dir,
            config / "vendor_health_policy.json",
        )

        self.agent_by_skill = {}
        for agent in self.skill_resolver.agent_registry["agents"]:
            for skill in agent.get("skills", []):
                self.agent_by_skill.setdefault(skill, []).append(agent)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="milliseconds")

    def execute(
        self,
        *,
        correlation_id: str,
        scenario_id: str,
        as_of: str | None = None,
    ) -> AdaptiveExecutionAssessment:
        self.policy_audit.clear()
        execution_id = f"EAIOSADAPT-{uuid.uuid4().hex[:12].upper()}"

        confidence = self.confidence_engine.assess(
            scenario_id,
            as_of=as_of,
        )
        initial_confidence = confidence
        plan = self.planner.plan_from_confidence(confidence)
        initial_plan = plan

        trace: list[SkillExecutionTrace] = []
        outputs: dict[str, dict] = {}
        completed_skills: list[str] = []
        executed_agents: list[str] = []
        runtime_signals: list[RuntimeEvidenceSignal] = []
        transitions: list[PlanTransition] = []
        reassessments: dict[str, dict] = {}
        # Width of every plan the run actually resolved, in order. Peak width
        # is read from here rather than inferred from execution, so an
        # excursion stays visible even when the plan returns to its start.
        plan_widths: list[int] = [plan.reasoning_agent_count]

        pending = list(plan.required_skills)
        while pending:
            skill_id = pending.pop(0)
            if skill_id in completed_skills:
                continue

            agent = self._agent_for_skill(plan, skill_id)
            result = self._execute_skill(
                sequence=len(trace) + 1,
                correlation_id=correlation_id,
                scenario_id=scenario_id,
                plan=plan,
                confidence=confidence,
                skill_id=skill_id,
                agent=agent,
                outputs=outputs,
                runtime_signals=runtime_signals,
                trace=trace,
            )
            outputs[skill_id] = result.output
            completed_skills.append(skill_id)
            executed_agents.append(agent.agent_id)
            runtime_signals.extend(result.runtime_signals)

            if skill_id in set(plan.reassess_after_skills):
                confidence, reassessment = self.reassessor.reassess(
                    confidence,
                    result.runtime_signals,
                )
                record = asdict(reassessment)
                reassessments[skill_id] = record
                # The unkeyed entry stays bound to the first reassessment so
                # existing consumers keep their meaning when a run reassesses
                # more than once.
                outputs.setdefault("confidence_reassessment", record)
                outputs["confidence_reassessments"] = dict(reassessments)
                updated_plan = self.planner.plan_from_confidence(confidence)

                if updated_plan.orchestration_mode != plan.orchestration_mode:
                    still_required = [
                        skill for skill in updated_plan.required_skills
                        if skill not in completed_skills
                    ]
                    # Narrowing is a substitution, not a truncation: skills the
                    # wider plan had queued are cancelled while the narrower
                    # plan introduces skills of its own. Completed work is
                    # never cancelled, only what is still pending.
                    cancelled_skills = [
                        skill for skill in pending
                        if skill not in updated_plan.required_skills
                    ]
                    contracted = len(updated_plan.required_skills) < len(
                        plan.required_skills
                    )
                    transitions.append(
                        PlanTransition(
                            from_mode=plan.orchestration_mode,
                            to_mode=updated_plan.orchestration_mode,
                            direction=(
                                "CONTRACTION" if contracted else "EXPANSION"
                            ),
                            triggered_after_skill=skill_id,
                            reason=reassessment.explanation,
                            completed_skills_retained=list(completed_skills),
                            added_skills=list(still_required),
                            cancelled_skills=cancelled_skills,
                        )
                    )
                    plan = updated_plan
                    plan_widths.append(updated_plan.reasoning_agent_count)
                    pending = list(still_required)

        recommendation_skill = (
            "governed_recommendation"
            if "governed_recommendation" in outputs
            else "evidence_fusion_recommendation"
        )
        recommendation = outputs[recommendation_skill]

        decision_counts: dict[str, int] = {}
        for decision in self.policy_audit:
            decision_counts[decision.decision] = (
                decision_counts.get(decision.decision, 0) + 1
            )

        readiness = self.readiness_evaluator.evaluate(confidence)

        return AdaptiveExecutionAssessment(
            execution_id=execution_id,
            correlation_id=correlation_id,
            scenario_id=scenario_id,
            scenario_name=plan.scenario_name,
            initial_plan_mode=initial_plan.orchestration_mode,
            final_plan_mode=plan.orchestration_mode,
            initial_confidence_score=initial_confidence.confidence_score,
            final_confidence_score=confidence.confidence_score,
            initial_confidence_level=initial_confidence.confidence_level,
            final_confidence_level=confidence.confidence_level,
            drift_status=confidence.drift_status,
            expanded_during_execution=any(
                transition.direction == "EXPANSION"
                for transition in transitions
            ),
            contracted_during_execution=any(
                transition.direction == "CONTRACTION"
                for transition in transitions
            ),
            plan_transitions=transitions,
            required_skills_initial=initial_plan.required_skills,
            required_skills_final=plan.required_skills,
            completed_skills=completed_skills,
            reasoning_agents_executed=executed_agents,
            reasoning_agent_execution_count=len(executed_agents),
            initial_agent_count=initial_plan.reasoning_agent_count,
            final_agent_count=len(dict.fromkeys(executed_agents)),
            initial_plan_agent_count=initial_plan.reasoning_agent_count,
            peak_plan_agent_count=max(plan_widths),
            final_plan_agent_count=plan.reasoning_agent_count,
            unique_agents_executed=len(dict.fromkeys(executed_agents)),
            automation_readiness=self.readiness_evaluator.to_dict(readiness),
            recommendation=recommendation,
            skill_outputs=outputs,
            execution_trace=trace,
            policy_decisions=list(self.policy_audit),
            policy_decision_counts=decision_counts,
            safety_status=recommendation["safety_status"],
            approval_state="AWAITING_APPROVAL",
            generated_at=self._now(),
        )

    def _agent_for_skill(
        self,
        plan: AdaptivePlan,
        skill_id: str,
    ) -> AgentSelection:
        matches = [
            agent for agent in plan.selected_agents
            if skill_id in agent.assigned_skills
        ]
        if matches:
            return matches[0]

        # An expanded plan may contain a different selection set.
        resolution = self.skill_resolver.resolve([skill_id])
        if not resolution.selected_agents:
            raise RuntimeError(f"No active agent provides {skill_id}.")
        return resolution.selected_agents[0]

    def _request(
        self,
        *,
        correlation_id: str,
        request_type: str,
        agent_id: str,
        action: str,
        resource_id: str,
        skill_id: str,
        operation_mode: str,
        data_domain: str | None = None,
    ) -> PolicyRequest:
        return PolicyRequest(
            correlation_id=correlation_id,
            request_type=request_type,
            requesting_agent_id=agent_id,
            action=action,
            resource_id=resource_id,
            skill_id=skill_id,
            operation_mode=operation_mode,
            data_domain=data_domain,
            data_classification="SYNTHETIC",
            purpose="operational_assessment",
        )

    def _execute_skill(
        self,
        *,
        sequence: int,
        correlation_id: str,
        scenario_id: str,
        plan: AdaptivePlan,
        confidence: OperationalConfidenceAssessment,
        skill_id: str,
        agent: AgentSelection,
        outputs: dict[str, dict],
        runtime_signals: list[RuntimeEvidenceSignal],
        trace: list[SkillExecutionTrace],
    ) -> SkillExecutionResult:
        started_at = self._now()
        started = perf_counter()
        decision_ids: list[str] = []

        try:
            a2a = self.a2a_pep.enforce(
                self._request(
                    correlation_id=correlation_id,
                    request_type="A2A",
                    agent_id=agent.agent_id,
                    action="delegate_skill",
                    resource_id=agent.agent_id,
                    skill_id=skill_id,
                    operation_mode="DELEGATE",
                )
            )
            decision_ids.append(a2a.decision_id)

            result = self._dispatch_skill(
                correlation_id=correlation_id,
                scenario_id=scenario_id,
                plan=plan,
                confidence=confidence,
                skill_id=skill_id,
                agent=agent,
                outputs=outputs,
                runtime_signals=runtime_signals,
                decision_ids=decision_ids,
            )
        except Exception as exc:
            trace.append(
                SkillExecutionTrace(
                    sequence=sequence,
                    skill_id=skill_id,
                    agent_id=agent.agent_id,
                    agent_name=agent.agent_name,
                    status="FAILED",
                    started_at=started_at,
                    completed_at=self._now(),
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                    summary="",
                    policy_decision_ids=decision_ids,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            raise

        trace.append(
            SkillExecutionTrace(
                sequence=sequence,
                skill_id=skill_id,
                agent_id=agent.agent_id,
                agent_name=agent.agent_name,
                status="SUCCEEDED",
                started_at=started_at,
                completed_at=self._now(),
                duration_ms=round((perf_counter() - started) * 1000, 3),
                summary=result.summary,
                policy_decision_ids=decision_ids,
                error=None,
            )
        )
        return result

    def _enforce_data(
        self,
        *,
        correlation_id: str,
        agent: AgentSelection,
        skill_id: str,
        domain: str,
        decision_ids: list[str],
    ) -> None:
        decision = self.data_pep.enforce(
            self._request(
                correlation_id=correlation_id,
                request_type="DATA",
                agent_id=agent.agent_id,
                action="read",
                resource_id=domain,
                skill_id=skill_id,
                operation_mode="READ",
                data_domain=domain,
            )
        )
        decision_ids.append(decision.decision_id)

    def _enforce_tool(
        self,
        *,
        correlation_id: str,
        agent: AgentSelection,
        skill_id: str,
        tool: str,
        operation_mode: str,
        decision_ids: list[str],
    ) -> PolicyDecision:
        decision = self.mcp_pep.enforce(
            self._request(
                correlation_id=correlation_id,
                request_type="MCP",
                agent_id=agent.agent_id,
                action="invoke_tool",
                resource_id=tool,
                skill_id=skill_id,
                operation_mode=operation_mode,
            )
        )
        decision_ids.append(decision.decision_id)
        return decision

    def _dispatch_skill(
        self,
        *,
        correlation_id: str,
        scenario_id: str,
        plan: AdaptivePlan,
        confidence: OperationalConfidenceAssessment,
        skill_id: str,
        agent: AgentSelection,
        outputs: dict[str, dict],
        runtime_signals: list[RuntimeEvidenceSignal],
        decision_ids: list[str],
    ) -> SkillExecutionResult:
        if skill_id == "semantic_context":
            self._enforce_data(
                correlation_id=correlation_id,
                agent=agent,
                skill_id=skill_id,
                domain="entity_registry",
                decision_ids=decision_ids,
            )
            self._enforce_data(
                correlation_id=correlation_id,
                agent=agent,
                skill_id=skill_id,
                domain="semantic_relationships",
                decision_ids=decision_ids,
            )
            self._enforce_tool(
                correlation_id=correlation_id,
                agent=agent,
                skill_id=skill_id,
                tool="semantic_graph.query",
                operation_mode="READ",
                decision_ids=decision_ids,
            )
            result = self.graph_agent.analyze(scenario_id)
            return SkillExecutionResult(
                skill_id=skill_id,
                agent_id=agent.agent_id,
                summary=result.explanation,
                output=asdict(result),
                runtime_signals=[],
            )

        if skill_id == "due_diligence_validation":
            for domain in (
                "health_observations",
                "known_errors",
                "outcome_history",
                "changes",
                "knowledge_metadata",
            ):
                self._enforce_data(
                    correlation_id=correlation_id,
                    agent=agent,
                    skill_id=skill_id,
                    domain=domain,
                    decision_ids=decision_ids,
                )
            for tool in (
                "telemetry.query_summary",
                "servicenow.query_recent_changes",
                "knowledge.query_metadata",
            ):
                self._enforce_tool(
                    correlation_id=correlation_id,
                    agent=agent,
                    skill_id=skill_id,
                    tool=tool,
                    operation_mode="READ",
                    decision_ids=decision_ids,
                )
            return self.due_diligence_agent.execute(
                scenario_id=scenario_id,
                confidence=confidence,
                graph_context=outputs["semantic_context"],
            )

        if skill_id == "detailed_telemetry_analysis":
            for domain in ("telemetry_samples", "metric_definitions"):
                self._enforce_data(
                    correlation_id=correlation_id,
                    agent=agent,
                    skill_id=skill_id,
                    domain=domain,
                    decision_ids=decision_ids,
                )
            self._enforce_tool(
                correlation_id=correlation_id,
                agent=agent,
                skill_id=skill_id,
                tool="telemetry.query_timeseries",
                operation_mode="READ",
                decision_ids=decision_ids,
            )
            result = self.telemetry_agent.analyze(scenario_id)
            return SkillExecutionResult(
                skill_id=skill_id,
                agent_id=agent.agent_id,
                summary=result.temporal_explanation,
                output=self.telemetry_agent.to_dict(result),
                runtime_signals=[],
            )

        if skill_id == "governed_knowledge_retrieval":
            for domain in (
                "knowledge_documents",
                "incidents",
                "problems",
                "changes",
            ):
                self._enforce_data(
                    correlation_id=correlation_id,
                    agent=agent,
                    skill_id=skill_id,
                    domain=domain,
                    decision_ids=decision_ids,
                )
            self._enforce_tool(
                correlation_id=correlation_id,
                agent=agent,
                skill_id=skill_id,
                tool="enterprise_search.retrieve",
                operation_mode="READ",
                decision_ids=decision_ids,
            )
            result = self.retrieval_agent.retrieve(scenario_id)
            return SkillExecutionResult(
                skill_id=skill_id,
                agent_id=agent.agent_id,
                summary=(
                    f"{len(result.accepted_free_text)} governed free-text, "
                    f"{len(result.accepted_structured_records)} structured, "
                    f"{len(result.rejected_candidates)} rejected."
                ),
                output=self.retrieval_agent.to_dict(result),
                runtime_signals=[],
            )

        if skill_id == "external_service_health":
            self._enforce_data(
                correlation_id=correlation_id,
                agent=agent,
                skill_id=skill_id,
                domain="vendor_advisories",
                decision_ids=decision_ids,
            )
            self._enforce_tool(
                correlation_id=correlation_id,
                agent=agent,
                skill_id=skill_id,
                tool="vendor_status.query",
                operation_mode="READ",
                decision_ids=decision_ids,
            )
            graph_context = outputs["semantic_context"]
            entity_ids = set(graph_context.get("authoritative_entity_ids", []))
            result = self.vendor_health_agent.assess(
                scenario_id=scenario_id,
                entity_ids=entity_ids,
                as_of=confidence.assessed_at,
            )
            required_vendors = self.confidence_engine.external_vendor_dependencies(
                confidence.observed_entity_id
            )
            signals = [
                RuntimeEvidenceSignal(
                    **row,
                    scenario_id=scenario_id,
                )
                for row in self.vendor_health_agent.signals_for(
                    result,
                    required_vendors=required_vendors,
                    entity_id=confidence.observed_entity_id,
                )
            ]
            output = self.vendor_health_agent.to_dict(result)
            output["required_vendor_dependencies"] = required_vendors
            return SkillExecutionResult(
                skill_id=skill_id,
                agent_id=agent.agent_id,
                summary=result.explanation,
                output=output,
                runtime_signals=signals,
            )

        if skill_id == "change_dependency_investigation":
            for domain in (
                "changes",
                "semantic_relationships",
                "business_context",
            ):
                self._enforce_data(
                    correlation_id=correlation_id,
                    agent=agent,
                    skill_id=skill_id,
                    domain=domain,
                    decision_ids=decision_ids,
                )
            for tool in (
                "servicenow.query_changes",
                "semantic_graph.query_dependencies",
            ):
                self._enforce_tool(
                    correlation_id=correlation_id,
                    agent=agent,
                    skill_id=skill_id,
                    tool=tool,
                    operation_mode="READ",
                    decision_ids=decision_ids,
                )
            return self.change_agent.execute(
                scenario_id=scenario_id,
                graph_context=outputs["semantic_context"],
                runtime_signals=runtime_signals,
            )

        if skill_id in {
            "governed_recommendation",
            "evidence_fusion_recommendation",
        }:
            domain = (
                "evidence_summary"
                if skill_id == "governed_recommendation"
                else "all_governed_evidence"
            )
            self._enforce_data(
                correlation_id=correlation_id,
                agent=agent,
                skill_id=skill_id,
                domain=domain,
                decision_ids=decision_ids,
            )
            # Creating an assessment is a write operation, so the PDP returns
            # ESCALATE with a human-approval obligation. The demo records the
            # escalation and creates only a local assessment contract.
            assessment_decision = self._enforce_tool(
                correlation_id=correlation_id,
                agent=agent,
                skill_id=skill_id,
                tool="servicenow.create_assessment",
                operation_mode="WRITE",
                decision_ids=decision_ids,
            )
            if assessment_decision.decision != "ESCALATE":
                raise RuntimeError(
                    "Assessment creation must remain an approval-bound escalation."
                )
            return self.recommendation_agent.execute(
                scenario_id=scenario_id,
                orchestration_mode=plan.orchestration_mode,
                plan_name=plan.plan_name,
                confidence=confidence,
                completed_outputs=outputs,
            )

        raise ValueError(f"No execution handler for skill {skill_id}.")

    @staticmethod
    def to_dict(result: AdaptiveExecutionAssessment) -> dict:
        return asdict(result)
