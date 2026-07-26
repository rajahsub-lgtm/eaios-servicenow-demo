from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from statistics import mean
import json

from case_fingerprint import CaseFingerprinter
from case_similarity import CaseSimilarity, resolve_policy
from documented_reasoning import (
    DocumentationReasoner,
    resolve_documentation_policy,
)
from knowledge_retrieval_agent import KnowledgeRetrievalAgent
from telemetry_agent import TelemetryAnalysisAgent


TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
CONFIDENCE_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
FAILURE_SIGNAL_PENALTY = {"LOW": 0.00, "MEDIUM": 0.03, "HIGH": 0.08}


@dataclass(frozen=True)
class OutcomeHistorySummary:
    known_error_id: str
    scenario_pattern: str
    occurrences: int
    successful_outcomes: int
    failed_outcomes: int
    success_rate: float
    recurrence_rate: float
    average_recovery_minutes: float
    average_evidence_usefulness: float
    dominant_prior_confidence: str


@dataclass(frozen=True)
class EvidenceContribution:
    evidence_id: str
    evidence_type: str
    evidence_class: str
    role: str
    reliability: float
    contribution: float
    rationale: str
    provenance: str


@dataclass(frozen=True)
class HypothesisAssessment:
    hypothesis_id: str
    hypothesis_type: str
    title: str
    applies_to_entity_id: str
    score: float
    confidence_level: str
    status: str
    historical_success_rate: float
    recent_failure_signal: str
    outcome_history: OutcomeHistorySummary
    supporting_evidence_ids: list[str]
    uncertainty_factors: list[str]
    # Populated when other evidence argues against this hypothesis. A retired
    # candidate keeps its score and its reason so the record shows what was
    # considered, not only what survived.
    contradicting_evidence_ids: tuple[str, ...] = ()
    rejection_reason: str = ""


@dataclass(frozen=True)
class EvidenceFusionAssessment:
    scenario_id: str
    scenario_name: str
    trigger_observation_id: str
    trigger_observed_at: str
    selected_strategy: str
    confidence_level: str
    confidence_score: float
    safety_status: str
    human_approval_required: bool
    leading_hypothesis: HypothesisAssessment
    alternative_hypotheses: list[HypothesisAssessment]
    recommended_action: str
    validation_steps: list[str]
    evidence_ledger: list[EvidenceContribution]
    rejected_evidence_ids: list[str]
    uncertainty_factors: list[str]
    guardrail_reasons: list[str]
    reasoning_summary: str


class EvidenceFusionAgent:
    """Fuse governed graph, telemetry, retrieval, and outcome evidence.

    The strategy is derived from evidence quality and convergence. Scenario
    `expected_*` fields are test oracles only and are never used for selection.
    """

    def __init__(self, json_dir: str | Path) -> None:
        self.json_dir = Path(json_dir)
        self.telemetry_agent = TelemetryAnalysisAgent(self.json_dir)
        self.retrieval_agent = KnowledgeRetrievalAgent(self.json_dir)
        self.fingerprinter = CaseFingerprinter(self.json_dir)
        self.similarity = CaseSimilarity(resolve_policy(self.json_dir))
        self.documentation = DocumentationReasoner(
            self.json_dir, resolve_documentation_policy(self.json_dir)
        )

        self.scenarios = self._load("scenarios.json")
        self.known_errors = self._load("known_errors.json")
        learned_path = self.json_dir / "learned_patterns.json"
        if learned_path.exists():
            with open(learned_path, encoding="utf-8") as f:
                self.known_errors.extend(json.load(f))
        self.outcomes = self._load("outcome_history.json")
        self.changes = self._load("changes.json")

        self.scenario_by_id = {row["scenario_id"]: row for row in self.scenarios}
        self.known_error_by_id = {
            row["known_error_id"]: row for row in self.known_errors
        }

    def _load(self, filename: str) -> list[dict]:
        with open(self.json_dir / filename, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _dt(value: str) -> datetime:
        return datetime.strptime(value, TIME_FORMAT)

    @staticmethod
    def _confidence(score: float) -> str:
        if score >= 0.85:
            return "HIGH"
        if score >= 0.55:
            return "MEDIUM"
        return "LOW"

    def _outcome_summary(
        self, known_error_id: str, scenario_pattern: str
    ) -> OutcomeHistorySummary:
        rows = [
            row for row in self.outcomes
            if row["known_error_id"] == known_error_id
            and row["scenario_pattern"] == scenario_pattern
        ]

        if not rows:
            return OutcomeHistorySummary(
                known_error_id=known_error_id,
                scenario_pattern=scenario_pattern,
                occurrences=0,
                successful_outcomes=0,
                failed_outcomes=0,
                success_rate=0.0,
                recurrence_rate=0.0,
                average_recovery_minutes=0.0,
                average_evidence_usefulness=0.0,
                dominant_prior_confidence="LOW",
            )

        successes = sum(row["outcome"] == "Successful" for row in rows)
        failures = len(rows) - successes
        recurrences = sum(bool(row["recurrence_within_24h"]) for row in rows)
        confidence_counts: dict[str, int] = {}
        for row in rows:
            level = row.get("prior_confidence", "LOW")
            confidence_counts[level] = confidence_counts.get(level, 0) + 1

        dominant = max(
            confidence_counts,
            key=lambda level: (
                confidence_counts[level],
                CONFIDENCE_ORDER.get(level, 0),
            ),
        )

        return OutcomeHistorySummary(
            known_error_id=known_error_id,
            scenario_pattern=scenario_pattern,
            occurrences=len(rows),
            successful_outcomes=successes,
            failed_outcomes=failures,
            success_rate=round(successes / len(rows), 3),
            recurrence_rate=round(recurrences / len(rows), 3),
            average_recovery_minutes=round(
                mean(float(row["recovery_minutes"]) for row in rows), 2
            ),
            average_evidence_usefulness=round(
                mean(float(row["evidence_usefulness_score"]) for row in rows), 2
            ),
            dominant_prior_confidence=dominant,
        )

    def _recent_high_risk_changes(
        self, scenario_id: str, trigger_time: datetime
    ) -> list[dict]:
        result = []
        for row in self.changes:
            if row["scenario_id"] != scenario_id:
                continue
            implemented = self._dt(row["implemented_at"])
            age_hours = (trigger_time - implemented).total_seconds() / 3600
            if (
                0 <= age_hours <= 4
                and row["risk"] == "High"
                and row["state"] == "Closed Successful"
            ):
                result.append(row)
        return result

    @staticmethod
    def _critical_application_services(telemetry) -> set[str]:
        return {
            summary.entity_id
            for summary in telemetry.metric_summaries
            if summary.current_status == "CRITICAL"
            and summary.entity_id.startswith("AS-")
        }

    @staticmethod
    def _accepted_evidence_ids(retrieval) -> set[str]:
        return {
            candidate.source_id
            for candidate in (
                list(retrieval.accepted_free_text)
                + list(retrieval.accepted_structured_records)
            )
        }

    def _known_error_candidates(
        self,
        *,
        retrieval,
        telemetry,
        recent_high_risk_changes: list[dict],
    ) -> list[HypothesisAssessment]:
        authoritative_ids = set(retrieval.authoritative_entity_ids)
        symptoms = set(retrieval.symptom_categories)
        case_fingerprint = self.fingerprinter.for_observation(
            self.retrieval_agent.observation_by_id[retrieval.trigger_observation_id]
        )
        accepted_ids = self._accepted_evidence_ids(retrieval)
        critical_metrics = [
            summary for summary in telemetry.metric_summaries
            if summary.current_status == "CRITICAL"
        ]
        critical_services = self._critical_application_services(telemetry)

        candidates: list[HypothesisAssessment] = []
        for known_error in self.known_errors:
            # Mirrors the confidence engine's admissibility. The layers
            # disagreeing about what is recallable is how a plan gets chosen
            # on a premise the next stage refuses.
            if known_error["knowledge_status"] not in {"Active", "Provisional"}:
                continue
            if known_error["trust_level"] not in {"Trusted", "Provisional"}:
                continue
            # Recall by presentation, matching the confidence engine. Testing
            # entity membership and symptom equality separately reproduces the
            # disagreement this model exists to remove: one layer recognising a
            # pattern the other cannot see.
            match = self.similarity.compare(
                case_fingerprint, self.fingerprinter.for_known_error(known_error)
            )
            if match.score < self.similarity.floor:
                continue

            history = self._outcome_summary(
                known_error["known_error_id"],
                known_error["symptom_category"],
            )

            direct_applicability = 1.0
            symptom_match = 1.0
            telemetry_corroboration = min(1.0, len(critical_metrics) / 4)
            governed_knowledge_support = (
                1.0
                if any(
                    known_error["known_error_id"] in candidate.entity_overlap
                    or known_error["applies_to_entity_id"] in candidate.entity_overlap
                    for candidate in retrieval.accepted_free_text
                )
                else 0.65
            )
            outcome_success = history.success_rate
            history_depth = min(1.0, history.occurrences / 20)

            base_score = (
                0.20 * direct_applicability
                + 0.15 * symptom_match
                + 0.15 * telemetry_corroboration
                + 0.15 * governed_knowledge_support
                + 0.25 * outcome_success
                + 0.10 * history_depth
            )

            uncertainty: list[str] = []
            penalty = FAILURE_SIGNAL_PENALTY.get(
                known_error.get("recent_failure_signal", "LOW"), 0.08
            )
            if known_error.get("recent_failure_signal") in {"MEDIUM", "HIGH"}:
                uncertainty.append(
                    f"KNOWN_ERROR_RECENT_FAILURE_SIGNAL_"
                    f"{known_error['recent_failure_signal']}"
                )

            if recent_high_risk_changes:
                penalty += 0.08
                uncertainty.append("RECENT_HIGH_RISK_CHANGE")

            if retrieval.hypothesis_entity_ids:
                penalty += 0.05
                uncertainty.append("INFERRED_CHANGE_OR_CAUSAL_HYPOTHESIS")

            if len(critical_services) >= 2:
                penalty += 0.07
                uncertainty.append("CROSS_SERVICE_DEGRADATION")

            if history.success_rate < 0.90:
                penalty += 0.03
                uncertainty.append("HISTORICAL_SUCCESS_BELOW_ACCELERATION_THRESHOLD")

            if history.recurrence_rate >= 0.15:
                penalty += 0.02
                uncertainty.append("ELEVATED_RECURRENCE_RATE")

            score = round(max(0.0, min(1.0, base_score - penalty)), 3)

            supporting_ids = sorted(
                {
                    candidate.source_id
                    for candidate in (
                        list(retrieval.accepted_free_text)
                        + list(retrieval.accepted_structured_records)
                    )
                    if (
                        known_error["known_error_id"] in candidate.entity_overlap
                        or known_error["applies_to_entity_id"] in candidate.entity_overlap
                        or known_error["symptom_category"] in candidate.symptom_overlap
                    )
                }
                | {
                    known_error["known_error_id"],
                    telemetry.trigger_observation_id,
                }
            )

            candidates.append(
                HypothesisAssessment(
                    hypothesis_id=known_error["known_error_id"],
                    hypothesis_type="KNOWN_ERROR",
                    title=known_error["title"],
                    applies_to_entity_id=known_error["applies_to_entity_id"],
                    score=score,
                    confidence_level=self._confidence(score),
                    status="CANDIDATE",
                    historical_success_rate=float(
                        known_error["historical_success_rate_numeric"]
                    ),
                    recent_failure_signal=known_error["recent_failure_signal"],
                    outcome_history=history,
                    supporting_evidence_ids=supporting_ids,
                    uncertainty_factors=uncertainty,
                )
            )

        candidates.sort(
            key=lambda item: (
                item.score,
                item.outcome_history.success_rate,
                item.outcome_history.occurrences,
            ),
            reverse=True,
        )
        return candidates

    def _change_hypotheses(
        self,
        *,
        retrieval,
        recent_high_risk_changes: list[dict],
    ) -> list[HypothesisAssessment]:
        hypotheses = []
        accepted_ids = self._accepted_evidence_ids(retrieval)
        for change in recent_high_risk_changes:
            direct_graph_hypothesis = change["change_id"] in set(
                retrieval.hypothesis_entity_ids
            )
            score = 0.55 if direct_graph_hypothesis else 0.45
            uncertainty = [
                "TEMPORAL_CORRELATION_IS_NOT_CAUSATION",
                "CHANGE_STATE_CLOSED_SUCCESSFUL_DOES_NOT_PROVE_SAFETY",
            ]
            hypotheses.append(
                HypothesisAssessment(
                    hypothesis_id=change["change_id"],
                    hypothesis_type="CHANGE_CORRELATION",
                    title=change["short_description"],
                    applies_to_entity_id=change["entity_id"],
                    score=score,
                    confidence_level=self._confidence(score),
                    status="CANDIDATE",
                    historical_success_rate=0.0,
                    recent_failure_signal="NOT_APPLICABLE",
                    outcome_history=OutcomeHistorySummary(
                        known_error_id="",
                        scenario_pattern="",
                        occurrences=0,
                        successful_outcomes=0,
                        failed_outcomes=0,
                        success_rate=0.0,
                        recurrence_rate=0.0,
                        average_recovery_minutes=0.0,
                        average_evidence_usefulness=0.0,
                        dominant_prior_confidence="LOW",
                    ),
                    supporting_evidence_ids=sorted(
                        {
                            change["change_id"],
                            *(
                                [change["change_id"]]
                                if change["change_id"] in accepted_ids
                                else []
                            ),
                        }
                    ),
                    uncertainty_factors=uncertainty,
                )
            )
        return hypotheses

    @staticmethod
    def _mark_hypothesis(
        hypothesis: HypothesisAssessment, status: str
    ) -> HypothesisAssessment:
        # A hypothesis retired on evidence stays retired. Ranking decides which
        # candidate leads; it does not revive one that was ruled out.
        if hypothesis.status == "REJECTED":
            return hypothesis
        data = asdict(hypothesis)
        data["status"] = status
        data["outcome_history"] = hypothesis.outcome_history
        return HypothesisAssessment(**data)

    def _evidence_ledger(
        self,
        *,
        retrieval,
        telemetry,
        leading: HypothesisAssessment,
        recent_changes: list[dict],
        vendor_health: dict | None = None,
    ) -> list[EvidenceContribution]:
        ledger: list[EvidenceContribution] = list(
            self._vendor_contributions(vendor_health)
        )

        ledger.append(
            EvidenceContribution(
                evidence_id=telemetry.trigger_observation_id,
                evidence_type="HEALTH_OBSERVATION",
                evidence_class="OBSERVED_TELEMETRY",
                role="SUPPORTS",
                reliability=1.0,
                contribution=0.15,
                rationale=(
                    f"Trigger metric {telemetry.trigger_metric_summary.metric_name} "
                    f"is {telemetry.trigger_metric_summary.current_status} and "
                    f"rising at the governed trigger time."
                ),
                provenance=telemetry.trigger_metric_summary.source_system,
            )
        )

        ledger.append(
            EvidenceContribution(
                evidence_id=f"GRAPH:{leading.applies_to_entity_id}",
                evidence_type="SEMANTIC_GRAPH",
                evidence_class="AUTHORITATIVE_RELATIONSHIP",
                role="SUPPORTS",
                reliability=1.0,
                contribution=0.20,
                rationale=(
                    f"{leading.hypothesis_id} is applicable to the graph-resolved "
                    f"entity {leading.applies_to_entity_id}."
                ),
                provenance="Synthetic governed semantic relationships",
            )
        )

        history = leading.outcome_history
        ledger.append(
            EvidenceContribution(
                evidence_id=f"OUTCOME_HISTORY:{leading.hypothesis_id}",
                evidence_type="OUTCOME_HISTORY",
                evidence_class="COLLECTIVE_LEARNING",
                role="SUPPORTS" if history.success_rate >= 0.75 else "UNCERTAINTY",
                reliability=min(1.0, history.occurrences / 20),
                contribution=round(0.25 * history.success_rate, 3),
                rationale=(
                    f"{history.successful_outcomes}/{history.occurrences} prior "
                    f"outcomes succeeded; recurrence rate "
                    f"{history.recurrence_rate:.1%}; prior confidence was "
                    f"{history.dominant_prior_confidence}."
                ),
                provenance="Synthetic EAIOS outcome history",
            )
        )

        for candidate in retrieval.accepted_free_text[:5]:
            ledger.append(
                EvidenceContribution(
                    evidence_id=candidate.source_id,
                    evidence_type=candidate.source_type,
                    evidence_class=candidate.evidence_class,
                    role="SUPPORTS",
                    reliability=1.0,
                    contribution=round(min(0.12, candidate.score / 250), 3),
                    rationale=(
                        f"Governed free-text evidence passed publication, trust, "
                        f"safety, staleness, and relevance gates."
                    ),
                    provenance=candidate.provenance,
                )
            )

        for candidate in retrieval.accepted_structured_records[:5]:
            ledger.append(
                EvidenceContribution(
                    evidence_id=candidate.source_id,
                    evidence_type=candidate.source_type,
                    evidence_class=candidate.evidence_class,
                    role="CONTEXT",
                    reliability=1.0,
                    contribution=round(min(0.08, candidate.score / 250), 3),
                    rationale=(
                        "Approved structured enterprise record existed at the "
                        "trigger time and is relevant to the graph neighborhood."
                    ),
                    provenance=candidate.provenance,
                )
            )

        for change in recent_changes:
            ledger.append(
                EvidenceContribution(
                    evidence_id=change["change_id"],
                    evidence_type="CHANGE",
                    evidence_class="STRUCTURED_ENTERPRISE_RECORD",
                    role="UNCERTAINTY",
                    reliability=1.0,
                    contribution=-0.12,
                    rationale=(
                        "A high-risk change occurred within four hours of the "
                        "trigger. It is a leading hypothesis, not proof of cause."
                    ),
                    provenance="Synthetic Change Management",
                )
            )

        return ledger

    def _vendor_contributions(
        self, vendor_health: dict | None
    ) -> list[EvidenceContribution]:
        """Vendor findings entered as evidence in their own right.

        A vendor establishing its own health does not identify an internal
        cause, but it does argue against the external explanation, which is a
        contribution to the reasoning and belongs in the ledger.
        """
        if not vendor_health:
            return []
        contributions = []
        for finding in vendor_health.get("findings", []) or []:
            if not finding.get("eliminates_external_hypothesis"):
                continue
            vendor = finding.get("vendor", "")
            contributions.append(
                EvidenceContribution(
                    evidence_id=finding.get("advisory_id", ""),
                    evidence_type="VENDOR_HEALTH",
                    evidence_class="EXTERNAL_SERVICE_ATTESTATION",
                    role="CONTRADICTS",
                    reliability=float(finding.get("confidence", 0.0)),
                    contribution=0.08,
                    rationale=(
                        f"{vendor} reports {finding.get('service', 'its service')} "
                        f"operating normally on evidence {finding.get('freshness_minutes', 0)} "
                        f"minutes old from {finding.get('source_authority', 'an authority')}. "
                        "This argues against an external outage; it does not identify "
                        "an internal cause."
                    ),
                    provenance=finding.get("source_reference", ""),
                )
            )
        return contributions

    def _retire_external_hypotheses(
        self,
        candidates: list[HypothesisAssessment],
        vendor_health: dict | None,
    ) -> list[HypothesisAssessment]:
        """Retire external-outage candidates the vendor evidence rules out.

        Retirement requires every vendor the hypothesis covers to be
        established healthy. Partial coverage leaves the candidate standing,
        for the same reason partial coverage cannot clear the hard flag.
        """
        if not vendor_health:
            return candidates
        healthy = set(vendor_health.get("vendors_reporting_healthy", []) or [])
        required = set(vendor_health.get("required_vendor_dependencies", []) or [])
        if not required or not required.issubset(healthy):
            return candidates

        evidence_ids = tuple(
            finding.get("advisory_id", "")
            for finding in vendor_health.get("findings", []) or []
            if finding.get("eliminates_external_hypothesis")
        )
        retired = []
        for candidate in candidates:
            known_error = self.known_error_by_id.get(candidate.hypothesis_id, {})
            if known_error.get("hypothesis_class") != "EXTERNAL_VENDOR_OUTAGE":
                retired.append(candidate)
                continue
            retired.append(
                replace(
                    candidate,
                    score=round(candidate.score * 0.25, 3),
                    status="REJECTED",
                    contradicting_evidence_ids=evidence_ids,
                    rejection_reason=(
                        "Every external vendor this hypothesis depends on reports its "
                        f"own services healthy on fresh authoritative evidence: "
                        f"{', '.join(sorted(healthy))}."
                    ),
                )
            )
        return retired

    def _non_diagnosis(
        self,
        *,
        scenario,
        telemetry,
        retrieval,
        recent_changes: list[dict],
        vendor_health: dict | None,
    ) -> EvidenceFusionAssessment:
        """A governed account of not knowing.

        A clinician who concludes "I have not seen this before" has reached a
        finding, not a dead end: the finding is that no recorded pattern
        explains the presentation, and the correct next step is to gather
        rather than to treat. Recording it this way also lets the case enter
        outcome history, so the unexplained case becomes experience instead of
        being lost.
        """
        empty_history = OutcomeHistorySummary(
            known_error_id="", scenario_pattern="", occurrences=0,
            successful_outcomes=0, failed_outcomes=0, success_rate=0.0,
            recurrence_rate=0.0, average_recovery_minutes=0.0,
            average_evidence_usefulness=0.0, dominant_prior_confidence="LOW",
        )
        breaching = [
            summary.metric_id for summary in telemetry.metric_summaries
            if summary.current_status in {"HIGH", "CRITICAL"}
        ]
        no_diagnosis = HypothesisAssessment(
            hypothesis_id="NO_GOVERNED_PATTERN",
            hypothesis_type="NO_DIAGNOSIS",
            title="No recorded pattern accounts for this presentation",
            applies_to_entity_id=telemetry.metric_summaries[0].entity_id
            if telemetry.metric_summaries else "",
            score=0.0,
            confidence_level="LOW",
            status="NO_DIAGNOSIS",
            historical_success_rate=0.0,
            recent_failure_signal="NOT_APPLICABLE",
            outcome_history=empty_history,
            supporting_evidence_ids=[],
            uncertainty_factors=[
                "NO_COMPARABLE_RECORDED_EXPERIENCE",
                "PRESENTATION_UNMATCHED_BY_ANY_GOVERNED_PATTERN",
            ],
        )

        steps = [
            "Capture the full metric and dependency picture for the affected "
            "component before proposing any change.",
            "Confirm whether any recent change touches the component or its "
            "declared dependencies.",
            "Establish external service health for any vendor dependency in scope.",
            "Record the eventual resolution as a governed outcome so this "
            "presentation becomes recorded experience.",
        ]
        if recent_changes:
            steps.insert(
                1,
                "A recent high-risk change is in scope: establish whether it is "
                "correlated before treating it as causal.",
            )

        ledger = list(self._vendor_contributions(vendor_health))
        for metric_id in breaching[:4]:
            ledger.append(
                EvidenceContribution(
                    evidence_id=metric_id, evidence_type="TELEMETRY",
                    evidence_class="OBSERVED_SIGNAL", role="CONTEXT",
                    reliability=0.9, contribution=0.0,
                    rationale=(
                        "Breaching signal recorded as context. Without a "
                        "comparable pattern it establishes that something is "
                        "wrong, not what."
                    ),
                    provenance="Synthetic OpenTelemetry",
                )
            )

        return EvidenceFusionAssessment(
            scenario_id=scenario["scenario_id"],
            scenario_name=scenario["name"],
            trigger_observation_id=telemetry.trigger_observation_id,
            trigger_observed_at=telemetry.trigger_observed_at,
            selected_strategy="Full Investigation",
            confidence_level="LOW",
            confidence_score=0.0,
            safety_status="REQUIRES_HUMAN_APPROVAL",
            human_approval_required=True,
            leading_hypothesis=no_diagnosis,
            alternative_hypotheses=[],
            recommended_action=(
                "No governed pattern accounts for this presentation. Do not "
                "apply a remediation drawn from an unrelated pattern. Gather "
                "the evidence listed below and escalate to a human owner for "
                "direction."
            ),
            validation_steps=steps,
            evidence_ledger=ledger,
            rejected_evidence_ids=sorted(
                {c.source_id for c in retrieval.rejected_candidates}
            ),
            uncertainty_factors=[
                "NO_COMPARABLE_RECORDED_EXPERIENCE",
                "NO_LEADING_HYPOTHESIS",
            ],
            guardrail_reasons=[
                "NO_GOVERNED_PATTERN_ABOVE_SIMILARITY_FLOOR",
                "HUMAN_DIRECTION_REQUIRED",
            ],
            reasoning_summary=(
                "Nothing in recorded experience resembles this presentation "
                "closely enough to reason from. The absence of a match is "
                "itself the finding: the next step is to gather evidence, not "
                "to act on an analogy that does not hold."
            ),
        )

    @staticmethod
    def _rejection_disclosure(proposal) -> str:
        """State that a human rejected this before, and who.

        A prior rejection lowers what the account is worth; it does not remove
        it. Whoever sees this proposal next is entitled to know it has been
        put up and turned down, so they can weigh that judgement rather than
        unknowingly repeat or unknowingly defer to it.
        """
        if not proposal.prior_rejections:
            return ""
        who = ", ".join(proposal.rejected_by) or "a reviewer"
        times = (
            "once"
            if proposal.prior_rejections == 1
            else f"{proposal.prior_rejections} times"
        )
        return (
            f" This account has been rejected {times} before for this "
            f"component, by {who}. It is offered again because nothing else "
            f"accounts for the presentation, not because that judgement was "
            f"overruled; weigh it before confirming."
        )

    def _documented_diagnosis(
        self,
        *,
        scenario,
        telemetry,
        retrieval,
        recent_changes: list[dict],
        vendor_health: dict | None,
        proposals,
    ) -> EvidenceFusionAssessment:
        """A cause proposed from the written procedure, put up for validation.

        This is weaker than every other hypothesis path and says so in every
        field it fills: the score is held under the documentation ceiling, the
        status is PROPOSED rather than LEADING, and the action asks a human to
        confirm the account before anything is done to the system.
        """
        leading = proposals[0]
        score = self.documentation.confidence_for(leading)
        empty_history = OutcomeHistorySummary(
            known_error_id="", scenario_pattern="", occurrences=0,
            successful_outcomes=0, failed_outcomes=0, success_rate=0.0,
            recurrence_rate=0.0, average_recovery_minutes=0.0,
            average_evidence_usefulness=0.0, dominant_prior_confidence="LOW",
        )
        entity_id = (
            telemetry.metric_summaries[0].entity_id
            if telemetry.metric_summaries
            else ""
        )

        def hypothesis(item, status: str) -> HypothesisAssessment:
            return HypothesisAssessment(
                hypothesis_id=item.document_id,
                hypothesis_type="DOCUMENTED_NOT_EXPERIENCED",
                title=item.title,
                applies_to_entity_id=entity_id,
                score=self.documentation.confidence_for(item),
                confidence_level="LOW",
                status=status,
                historical_success_rate=0.0,
                recent_failure_signal="NOT_APPLICABLE",
                outcome_history=empty_history,
                supporting_evidence_ids=[item.document_id],
                uncertainty_factors=[
                    "NO_COMPARABLE_RECORDED_EXPERIENCE",
                    "CAUSE_PROPOSED_FROM_DOCUMENTATION_ONLY",
                ],
            )

        ledger = list(self._vendor_contributions(vendor_health))
        for item in proposals:
            ledger.append(
                EvidenceContribution(
                    evidence_id=item.document_id,
                    evidence_type="GOVERNED_KNOWLEDGE",
                    evidence_class="DOCUMENTED_PROCEDURE",
                    role="PROPOSES_CAUSE" if item is leading else "ALTERNATIVE",
                    reliability=item.dimensions.get("document_trust", 0.0),
                    contribution=item.support,
                    rationale=(
                        f"{item.document_type} owned by {item.owner}, trust "
                        f"{item.trust_level}, last validated "
                        f"{item.days_since_validation} days ago; covers "
                        f"{item.symptom_coverage:.0%} of the presenting "
                        f"symptoms. No outcome stands behind it."
                    ),
                    provenance=f"Governed knowledge document {item.document_id}",
                )
            )

        steps = [
            f"Validate the cause proposed by {leading.document_id} against the "
            f"live component before acting on it.",
            "Confirm whether any recent change touches the component or its "
            "declared dependencies.",
            "Record the human validation decision and the eventual resolution "
            "as a governed outcome, so this presentation becomes recorded "
            "experience rather than being read from the manual again.",
        ]
        if recent_changes:
            steps.insert(
                1,
                "A recent high-risk change is in scope: establish whether it "
                "is correlated before treating it as causal.",
            )

        return EvidenceFusionAssessment(
            scenario_id=scenario["scenario_id"],
            scenario_name=scenario["name"],
            trigger_observation_id=telemetry.trigger_observation_id,
            trigger_observed_at=telemetry.trigger_observed_at,
            selected_strategy="Full Investigation",
            confidence_level="LOW",
            confidence_score=score,
            safety_status="REQUIRES_HUMAN_APPROVAL",
            human_approval_required=True,
            leading_hypothesis=hypothesis(leading, "PROPOSED"),
            alternative_hypotheses=[
                hypothesis(item, "ALTERNATIVE") for item in proposals[1:]
            ],
            recommended_action=(
                f"Nothing comparable has been resolved on this system, so no "
                f"cause is drawn from experience. {leading.document_id} "
                f"({leading.document_type}, owned by {leading.owner}) covers "
                f"this presentation and proposes: {leading.recommended_action} "
                f"Treat this as a proposal for human validation, not a "
                f"diagnosis. Confirm the account against the live component "
                f"before any change, and record the decision so the next "
                f"occurrence is met with experience rather than a manual."
                + self._rejection_disclosure(leading)
            ),
            validation_steps=steps,
            evidence_ledger=ledger,
            rejected_evidence_ids=sorted(
                {c.source_id for c in retrieval.rejected_candidates}
            ),
            uncertainty_factors=[
                "CAUSE_PROPOSED_FROM_DOCUMENTATION_ONLY",
                "NO_COMPARABLE_RECORDED_EXPERIENCE",
            ],
            guardrail_reasons=[
                "DOCUMENTED_HYPOTHESIS_REQUIRES_HUMAN_VALIDATION",
                "NO_GOVERNED_PATTERN_ABOVE_SIMILARITY_FLOOR",
            ],
            reasoning_summary=(
                f"No recorded case resembles this presentation, so the written "
                f"procedure was consulted instead. {leading.document_id} "
                f"covers {leading.symptom_coverage:.0%} of the presenting "
                f"symptoms at trust {leading.trust_level}. Confidence is held "
                f"at {score:.3f} by the documentation ceiling, because a "
                f"procedure describes what should work, not what has."
            ),
        )

    def analyze(
        self,
        scenario_id: str,
        *,
        vendor_health: dict | None = None,
    ) -> EvidenceFusionAssessment:
        try:
            scenario = self.scenario_by_id[scenario_id]
        except KeyError as exc:
            raise KeyError(f"Unknown scenario: {scenario_id}") from exc

        telemetry = self.telemetry_agent.analyze(scenario_id)
        retrieval = self.retrieval_agent.retrieve(scenario_id)
        trigger_time = self._dt(telemetry.trigger_observed_at)
        recent_changes = self._recent_high_risk_changes(scenario_id, trigger_time)

        known_error_candidates = self._known_error_candidates(
            retrieval=retrieval,
            telemetry=telemetry,
            recent_high_risk_changes=recent_changes,
        )
        if not known_error_candidates:
            # Nothing recorded resembles this closely enough to reason from.
            # Before conceding that nothing is known, read what has been
            # written: a procedure is a basis for a proposal a human can
            # validate, which is how a first encounter becomes a second one.
            documented = self.documentation.propose(
                self.fingerprinter.for_scenario(scenario_id),
                assessed_at=trigger_time,
            )
            if documented:
                return self._documented_diagnosis(
                    scenario=scenario,
                    telemetry=telemetry,
                    retrieval=retrieval,
                    recent_changes=recent_changes,
                    vendor_health=vendor_health,
                    proposals=documented,
                )
            # Saying so is an answer; failing is not. The run produces an
            # investigative recommendation, holds no hypothesis, and escalates.
            return self._non_diagnosis(
                scenario=scenario,
                telemetry=telemetry,
                retrieval=retrieval,
                recent_changes=recent_changes,
                vendor_health=vendor_health,
            )

        known_error_candidates = self._retire_external_hypotheses(
            known_error_candidates, vendor_health
        )

        change_candidates = self._change_hypotheses(
            retrieval=retrieval,
            recent_high_risk_changes=recent_changes,
        )
        all_candidates = sorted(
            [*known_error_candidates, *change_candidates],
            key=lambda item: item.score,
            reverse=True,
        )

        leading = self._mark_hypothesis(all_candidates[0], "LEADING")
        alternatives = [
            self._mark_hypothesis(item, "ALTERNATIVE")
            for item in all_candidates[1:]
        ]

        uncertainty = sorted(
            {
                factor
                for candidate in all_candidates
                for factor in candidate.uncertainty_factors
            }
        )

        accelerated = (
            leading.hypothesis_type == "KNOWN_ERROR"
            and leading.score >= 0.85
            and leading.outcome_history.occurrences >= 10
            and leading.outcome_history.success_rate >= 0.90
            and leading.recent_failure_signal == "LOW"
            and not recent_changes
            and not retrieval.hypothesis_entity_ids
            and len(self._critical_application_services(telemetry)) < 2
        )

        selected_strategy = (
            "Known Error Accelerated Validation"
            if accelerated
            else "Full Investigation"
        )
        confidence_score = leading.score
        confidence_level = self._confidence(confidence_score)

        known_error = self.known_error_by_id.get(leading.hypothesis_id)
        if selected_strategy == "Known Error Accelerated Validation" and known_error:
            recommended_action = (
                f"Validate the leading known error before action: "
                f"{known_error['recommended_action']} "
                f"Do not execute remediation until ServiceNow approval is granted."
            )
            validation_steps = [
                "Confirm the graph-resolved component and affected business capability.",
                "Validate Payment Gateway health and current dependency latency.",
                "Validate database connection pressure and connector saturation.",
                "Confirm that no active deployment or recent change better explains the symptoms.",
                "Obtain ServiceNow human approval before any drain or restart.",
                "After action, verify timeout rate, HTTP 5xx rate, and P95 latency recover.",
            ]
        else:
            recommended_action = (
                f"Treat {leading.title} as a leading hypothesis, not a confirmed "
                f"root cause. Continue coordinated investigation across telemetry, "
                f"consumer configuration, recent changes, dependencies, and logs. "
                f"Prepare rollback, scaling, or restart options for human approval; "
                f"do not execute them autonomously."
            )
            validation_steps = [
                "Compare producer rate with aggregate consumer throughput.",
                "Validate consumer lag, retry behavior, partition balance, and dependency latency.",
                "Compare active consumer configuration with the approved baseline.",
                "Correlate the recent high-risk change without treating timing as proof.",
                "Confirm impact across Accounting, Fraud, Billing, and Reconciliation owners.",
                "Obtain ServiceNow approval before rollback, scaling, restart, or traffic changes.",
            ]

        human_approval_required = True
        safety_status = "REQUIRES_HUMAN_APPROVAL"
        guardrails = [
            "NO_AUTONOMOUS_RESTART_OR_ROLLBACK",
            "PRESERVE_EVIDENCE_PROVENANCE",
            "REJECT_UNTRUSTED_STALE_OR_UNSAFE_KNOWLEDGE",
            "DO_NOT_PROMOTE_CORRELATION_TO_CAUSATION",
            "SERVICENOW_APPROVAL_REQUIRED_BEFORE_ACTION",
        ]

        ledger = self._evidence_ledger(
            retrieval=retrieval,
            telemetry=telemetry,
            leading=leading,
            recent_changes=recent_changes,
            vendor_health=vendor_health,
        )

        rejected_ids = sorted(
            {candidate.source_id for candidate in retrieval.rejected_candidates}
        )

        reasoning_summary = (
            f"Selected {selected_strategy} with {confidence_level} confidence "
            f"({confidence_score:.3f}). The leading hypothesis is "
            f"{leading.hypothesis_id}: {leading.title}. "
            f"Outcome history contains {leading.outcome_history.occurrences} "
            f"comparable cases with "
            f"{leading.outcome_history.success_rate:.1%} success and "
            f"{leading.outcome_history.recurrence_rate:.1%} recurrence. "
            f"{len(retrieval.accepted_free_text)} governed free-text items and "
            f"{len(retrieval.accepted_structured_records)} structured records "
            f"were eligible for fusion; {len(retrieval.rejected_candidates)} "
            f"candidates were excluded by governance gates. "
            f"Human approval remains mandatory."
        )

        return EvidenceFusionAssessment(
            scenario_id=scenario_id,
            scenario_name=scenario["name"],
            trigger_observation_id=telemetry.trigger_observation_id,
            trigger_observed_at=telemetry.trigger_observed_at,
            selected_strategy=selected_strategy,
            confidence_level=confidence_level,
            confidence_score=confidence_score,
            safety_status=safety_status,
            human_approval_required=human_approval_required,
            leading_hypothesis=leading,
            alternative_hypotheses=alternatives,
            recommended_action=recommended_action,
            validation_steps=validation_steps,
            evidence_ledger=ledger,
            rejected_evidence_ids=rejected_ids,
            uncertainty_factors=uncertainty,
            guardrail_reasons=guardrails,
            reasoning_summary=reasoning_summary,
        )

    @staticmethod
    def to_dict(result: EvidenceFusionAssessment) -> dict:
        return asdict(result)
