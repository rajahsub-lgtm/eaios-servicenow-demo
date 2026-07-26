from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
import json
import math

from case_fingerprint import CaseFingerprinter
from case_similarity import CaseSimilarity, resolve_policy
from graph_engine import SemanticGraph


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class OutcomeProfile:
    sample_size: int
    sample_maturity: float
    weighted_success_rate: float
    weighted_recurrence_rate: float
    weighted_evidence_usefulness: float
    weighted_prior_confidence: float
    recent_success_rate: float
    recent_recurrence_rate: float
    prior_success_rate: float
    prior_recurrence_rate: float
    drift_status: str
    drift_reasons: list[str]
    reliability_score: float


@dataclass(frozen=True)
class ConfidenceCandidate:
    known_error_id: str
    title: str
    applies_to_entity_id: str
    symptom_category: str
    confidence_score: float
    confidence_level: str
    factor_scores: dict[str, float]
    penalty_scores: dict[str, float]
    evidence_coverage: float
    contradiction_level: float
    hard_flags: list[str]
    outcome_profile: OutcomeProfile
    governed_knowledge_ids: list[str]
    recent_high_risk_change_ids: list[str]
    # How this pattern came to be considered. Direct experience is firsthand;
    # transferred experience is an analogy and is discounted as one.
    similarity: float = 1.0
    experience_class: str = "DIRECT"
    similarity_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationalConfidenceAssessment:
    scenario_id: str
    scenario_name: str
    trigger_observation_id: str
    assessed_at: str
    observed_entity_id: str
    selected_known_error_id: str | None
    selected_known_error_title: str | None
    confidence_score: float
    confidence_level: str
    confidence_trend: str
    drift_status: str
    evidence_coverage: float
    contradiction_level: float
    candidate_margin: float
    hard_flags: list[str]
    factor_scores: dict[str, float]
    penalty_scores: dict[str, float]
    candidate_assessments: list[ConfidenceCandidate]
    explanation: str


class OperationalConfidenceEngine:
    """Generic confidence assessment driven by graph and enterprise evidence.

    Scenario expected-result fields are deliberately ignored. New known errors,
    outcome records, knowledge metadata, changes, and graph relationships change
    behavior without code changes.
    """

    def __init__(
        self,
        json_dir: str | Path,
        policy_file: str | Path,
    ) -> None:
        self.json_dir = Path(json_dir)
        self.policy = self._read(Path(policy_file))
        self.graph = SemanticGraph.from_json_directory(self.json_dir)
        self.fingerprinter = CaseFingerprinter(self.json_dir)
        self.similarity = CaseSimilarity(resolve_policy(self.json_dir))

        self.scenarios = self._load("scenarios.json")
        self.observations = self._load("health_observations.json")
        self.known_errors = self._load("known_errors.json")
        self.outcomes = self._load("outcome_history.json")
        feedback_path = self.json_dir / "runtime_outcome_feedback.json"
        if feedback_path.exists():
            feedback_rows = self._read(feedback_path)
            if not isinstance(feedback_rows, list):
                raise ValueError("runtime_outcome_feedback.json must contain a JSON array.")
            self.outcomes.extend(feedback_rows)
        self.changes = self._load("changes.json")
        self.knowledge = self._load("knowledge_documents.json")

        self.scenario_by_id = {row["scenario_id"]: row for row in self.scenarios}
        self.observation_by_id = {
            row["observation_id"]: row for row in self.observations
        }
        self.known_error_by_id = {
            row["known_error_id"]: row for row in self.known_errors
        }

    @staticmethod
    def _read(path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load(self, filename: str) -> list[dict]:
        return self._read(self.json_dir / filename)

    @staticmethod
    def _dt(value: str) -> datetime:
        return datetime.strptime(value, DATETIME_FORMAT)

    def _level(self, score: float) -> str:
        levels = self.policy["levels"]
        if score >= float(levels["HIGH"]):
            return "HIGH"
        if score >= float(levels["MEDIUM"]):
            return "MEDIUM"
        return "LOW"

    def external_vendor_dependencies(self, observed_entity_id: str) -> list[str]:
        """Vendors whose services the observed entity forms part of.

        Derived by traversal, not declared on the scenario. A service that
        depends on an external vendor starts with that vendor's status
        unestablished, and the engine can only know that by looking at the
        graph. Entities with no vendor-provided ancestor produce nothing, so
        wholly internal scenarios are unaffected.
        """
        if observed_entity_id not in self.graph.entities:
            return []
        reachable = self.graph.reachable_paths(
            observed_entity_id,
            max_hops=3,
            direction="in",
            predicates={"DEPENDS_ON", "ROUTED_THROUGH"},
            allowed_authorities={"AUTHORITATIVE"},
        )
        vendors = set()
        for entity_id in list(reachable) + [observed_entity_id]:
            attributes = self.graph.get_entity(entity_id).attributes
            if attributes.get("service_provider_type") == "EXTERNAL_VENDOR":
                vendor = str(attributes.get("vendor", "")).strip()
                if vendor:
                    vendors.add(vendor)
        return sorted(vendors)

    def _vendor_status_flags(self, observed_entity_id: str) -> list[str]:
        return (
            ["VENDOR_STATUS_UNKNOWN"]
            if self.external_vendor_dependencies(observed_entity_id)
            else []
        )

    def assess(
        self,
        scenario_id: str,
        *,
        as_of: str | None = None,
    ) -> OperationalConfidenceAssessment:
        try:
            scenario = self.scenario_by_id[scenario_id]
        except KeyError as exc:
            raise KeyError(f"Unknown scenario: {scenario_id}") from exc

        trigger_id = scenario["trigger_observation_id"]
        observation = self.observation_by_id[trigger_id]
        assessed_at = self._dt(as_of) if as_of else self._dt(observation["observed_at"])
        observed_entity_id = observation["entity_id"]

        candidates = self._applicable_known_errors(
            observed_entity_id=observed_entity_id,
            trigger_observation_id=trigger_id,
            assessed_at=assessed_at,
        )

        assessed_candidates = [
            self._assess_candidate(
                known_error=row,
                observation=observation,
                assessed_at=assessed_at,
                candidate_count=len(candidates),
                match=match,
            )
            for row, match in candidates
        ]
        assessed_candidates.sort(
            key=lambda item: (
                item.confidence_score,
                item.outcome_profile.sample_size,
                item.known_error_id,
            ),
            reverse=True,
        )

        if not assessed_candidates:
            hard_flags = ["NO_APPLICABLE_KNOWN_ERROR"] + self._vendor_status_flags(
                observed_entity_id
            )
            return OperationalConfidenceAssessment(
                scenario_id=scenario_id,
                scenario_name=scenario["name"],
                trigger_observation_id=trigger_id,
                assessed_at=assessed_at.strftime(DATETIME_FORMAT),
                observed_entity_id=observed_entity_id,
                selected_known_error_id=None,
                selected_known_error_title=None,
                confidence_score=0.0,
                confidence_level="LOW",
                confidence_trend="ERODING",
                drift_status="DETECTED",
                evidence_coverage=0.0,
                contradiction_level=1.0,
                candidate_margin=0.0,
                hard_flags=hard_flags,
                factor_scores={},
                penalty_scores={},
                candidate_assessments=[],
                explanation=(
                    "No active trusted known error was applicable through the "
                    "authoritative semantic graph, so full investigation is required."
                ),
            )

        selected = assessed_candidates[0]
        candidate_margin = (
            selected.confidence_score - assessed_candidates[1].confidence_score
            if len(assessed_candidates) > 1
            else 1.0
        )

        trend = {
            "NONE": "STABLE",
            "STABLE": "STABLE",
            "IMPROVING": "IMPROVING",
            "ERODING": "ERODING",
            "DETECTED": "ERODING",
        }.get(selected.outcome_profile.drift_status, "STABLE")

        explanation = (
            f"Selected {selected.known_error_id} from "
            f"{len(assessed_candidates)} graph-applicable candidate(s). "
            f"Confidence {selected.confidence_score:.3f} is based on graph "
            f"applicability, recency-weighted outcomes, governed knowledge "
            f"readiness, trigger support, evidence coverage, and data-driven "
            f"penalties. Drift is {selected.outcome_profile.drift_status}; "
            f"candidate margin is {candidate_margin:.3f}."
        )

        return OperationalConfidenceAssessment(
            scenario_id=scenario_id,
            scenario_name=scenario["name"],
            trigger_observation_id=trigger_id,
            assessed_at=assessed_at.strftime(DATETIME_FORMAT),
            observed_entity_id=observed_entity_id,
            selected_known_error_id=selected.known_error_id,
            selected_known_error_title=selected.title,
            confidence_score=selected.confidence_score,
            confidence_level=selected.confidence_level,
            confidence_trend=trend,
            drift_status=selected.outcome_profile.drift_status,
            evidence_coverage=selected.evidence_coverage,
            contradiction_level=selected.contradiction_level,
            candidate_margin=round(max(0.0, candidate_margin), 3),
            hard_flags=sorted(
                set(selected.hard_flags)
                | set(self._vendor_status_flags(observed_entity_id))
                # Recognising a pattern by analogy is not the same as having
                # treated it here. Borrowed confidence may justify a
                # hypothesis; it does not justify a shortened investigation.
                | ({"EXPERIENCE_TRANSFERRED_NOT_DIRECT"}
                   if selected.experience_class == "TRANSFERRED" else set())
            ),
            factor_scores=selected.factor_scores,
            penalty_scores=selected.penalty_scores,
            candidate_assessments=assessed_candidates,
            explanation=explanation,
        )

    def _applicable_known_errors(
        self,
        *,
        observed_entity_id: str,
        trigger_observation_id: str,
        assessed_at: datetime,
    ) -> list[tuple[dict, object]]:
        """Recall patterns that resemble this case, with how alike each is.

        Retrieval used to ask whether an APPLIES_TO edge reached the observed
        entity, which is a question about filing rather than resemblance. It
        answered yes for a familiar component presenting an unfamiliar symptom,
        and no for an identical symptom on a structural sibling.

        Every active trusted pattern is now compared by presentation, and those
        clearing the similarity floor are returned with their score. Recall is
        graded, so the assessment can distinguish what it has seen here from
        what it has only seen somewhere like here.
        """
        observation = self.observation_by_id[trigger_observation_id]
        case = self.fingerprinter.for_observation(observation)

        matches: list[tuple[dict, object]] = []
        for known_error in self.known_errors:
            if known_error.get("knowledge_status") != "Active":
                continue
            if known_error.get("trust_level") != "Trusted":
                continue
            valid_from = datetime.strptime(known_error["valid_from"], "%Y-%m-%d")
            if valid_from > assessed_at:
                continue
            valid_to = known_error.get("valid_to", "")
            if valid_to and datetime.strptime(valid_to, "%Y-%m-%d") < assessed_at:
                continue

            remembered = self.fingerprinter.for_known_error(known_error)
            match = self.similarity.compare(case, remembered)
            if match.score >= self.similarity.floor:
                matches.append((known_error, match))

        matches.sort(key=lambda pair: pair[1].score, reverse=True)
        return matches

    def _assess_candidate(
        self,
        *,
        known_error: dict,
        observation: dict,
        assessed_at: datetime,
        candidate_count: int,
        match=None,
    ) -> ConfidenceCandidate:
        policy_weights = self.policy["weights"]
        thresholds = self.policy["thresholds"]
        penalty_policy = self.policy["penalties"]

        outcome_profile = self._outcome_profile(
            known_error_id=known_error["known_error_id"],
            assessed_at=assessed_at,
        )
        knowledge_ids, knowledge_readiness = self._governed_knowledge(
            known_error=known_error,
            assessed_at=assessed_at,
        )
        recent_high_risk_changes = self._recent_high_risk_changes(
            entity_id=known_error["applies_to_entity_id"],
            assessed_at=assessed_at,
        )

        # Applicability is how alike this case is to the remembered one, not
        # whether an edge happens to reach it. A pattern recognised by analogy
        # contributes proportionally less than one recognised firsthand.
        graph_applicability = 1.0 if match is None else match.score
        trigger_support = self._trigger_support(known_error, observation)

        evidence_components = [
            graph_applicability > 0.0,
            outcome_profile.sample_size > 0,
            knowledge_readiness > 0.0,
            trigger_support > 0.0,
        ]
        evidence_coverage = sum(evidence_components) / len(evidence_components)

        contradiction = 0.0
        hard_flags: list[str] = []
        penalties: dict[str, float] = {}

        failure_signal = known_error.get("recent_failure_signal", "LOW")
        if failure_signal in {"MEDIUM", "HIGH"}:
            key = f"recent_failure_signal_{failure_signal}"
            penalties[key] = float(
                penalty_policy[f"recent_failure_signal_{failure_signal}"]
            )

        if recent_high_risk_changes:
            penalties["recent_high_risk_change"] = float(
                penalty_policy["recent_high_risk_change"]
            )
            contradiction += 0.35
            hard_flags.append("RECENT_HIGH_RISK_CHANGE")

        minimum_sample = int(thresholds["minimum_outcome_sample"])
        if outcome_profile.sample_size < minimum_sample:
            penalties["insufficient_outcome_sample"] = float(
                penalty_policy["insufficient_outcome_sample"]
            )
            hard_flags.append("INSUFFICIENT_OUTCOME_HISTORY")

        if candidate_count > 1:
            penalties["candidate_ambiguity"] = min(
                0.15,
                float(penalty_policy["candidate_ambiguity"])
                * (candidate_count - 1),
            )
            contradiction += min(0.30, 0.10 * (candidate_count - 1))

        if outcome_profile.drift_status == "ERODING":
            penalties["eroding_confidence"] = float(
                penalty_policy["eroding_confidence"]
            )
            contradiction += 0.30

        if not knowledge_ids:
            penalties["stale_or_missing_governed_knowledge"] = float(
                penalty_policy["stale_or_missing_governed_knowledge"]
            )
            hard_flags.append("MISSING_GOVERNED_KNOWLEDGE")

        factors = {
            "graph_applicability": round(graph_applicability, 3),
            "outcome_reliability": round(outcome_profile.reliability_score, 3),
            "knowledge_readiness": round(knowledge_readiness, 3),
            "trigger_support": round(trigger_support, 3),
            "evidence_coverage": round(evidence_coverage, 3),
        }

        raw_score = sum(
            factors[name] * float(policy_weights[name])
            for name in policy_weights
        )
        score = max(0.0, min(1.0, raw_score - sum(penalties.values())))

        return ConfidenceCandidate(
            known_error_id=known_error["known_error_id"],
            title=known_error["title"],
            applies_to_entity_id=known_error["applies_to_entity_id"],
            symptom_category=known_error["symptom_category"],
            confidence_score=round(score, 3),
            confidence_level=self._level(score),
            factor_scores=factors,
            penalty_scores={k: round(v, 3) for k, v in penalties.items()},
            evidence_coverage=round(evidence_coverage, 3),
            contradiction_level=round(min(1.0, contradiction), 3),
            hard_flags=sorted(set(hard_flags)),
            outcome_profile=outcome_profile,
            governed_knowledge_ids=knowledge_ids,
            recent_high_risk_change_ids=[
                row["change_id"] for row in recent_high_risk_changes
            ],
            similarity=round(graph_applicability, 3),
            experience_class=(
                "DIRECT" if match is None or match.is_direct else "TRANSFERRED"
            ),
            similarity_reasons=tuple(match.reasons) if match else (),
        )

    def _outcome_profile(
        self,
        *,
        known_error_id: str,
        assessed_at: datetime,
    ) -> OutcomeProfile:
        rows = [
            row for row in self.outcomes
            if row["known_error_id"] == known_error_id
            and self._dt(row["recorded_at"]) <= assessed_at
        ]
        rows.sort(key=lambda row: self._dt(row["recorded_at"]))

        if not rows:
            return OutcomeProfile(
                sample_size=0,
                sample_maturity=0.0,
                weighted_success_rate=0.0,
                weighted_recurrence_rate=1.0,
                weighted_evidence_usefulness=0.0,
                weighted_prior_confidence=0.0,
                recent_success_rate=0.0,
                recent_recurrence_rate=1.0,
                prior_success_rate=0.0,
                prior_recurrence_rate=1.0,
                drift_status="ERODING",
                drift_reasons=["NO_OUTCOME_HISTORY"],
                reliability_score=0.0,
            )

        weighting = self.policy["recency_weighting"]
        half_life = float(weighting["half_life_days"])
        weights = []
        for row in rows:
            if weighting.get("enabled", True):
                age_days = max(
                    0.0,
                    (assessed_at - self._dt(row["recorded_at"])).total_seconds()
                    / 86400,
                )
                weight = 0.5 ** (age_days / half_life)
            else:
                weight = 1.0
            weights.append(weight)

        def weighted_average(values: list[float]) -> float:
            denominator = sum(weights)
            return (
                sum(value * weight for value, weight in zip(values, weights))
                / denominator
                if denominator
                else 0.0
            )

        confidence_value = {"HIGH": 1.0, "MEDIUM": 0.65, "LOW": 0.30}
        weighted_success = weighted_average(
            [1.0 if row["outcome"] == "Successful" else 0.0 for row in rows]
        )
        weighted_recurrence = weighted_average(
            [1.0 if row["recurrence_within_24h"] else 0.0 for row in rows]
        )
        weighted_usefulness = weighted_average(
            [float(row["evidence_usefulness_score"]) / 100.0 for row in rows]
        )
        weighted_prior_confidence = weighted_average(
            [confidence_value.get(row.get("prior_confidence", "LOW"), 0.30) for row in rows]
        )

        outcome_weights = self.policy["outcome_reliability_weights"]
        base_reliability = (
            weighted_success * float(outcome_weights["success_rate"])
            + (1.0 - weighted_recurrence)
            * float(outcome_weights["inverse_recurrence"])
            + weighted_usefulness
            * float(outcome_weights["evidence_usefulness"])
            + weighted_prior_confidence
            * float(outcome_weights["prior_confidence_calibration"])
        )

        # Outcome quality and outcome quantity are separate signals. A handful
        # of successes may be encouraging, but should not carry the same
        # reliability weight as a mature sample. The policy's minimum sample
        # defines when outcome evidence reaches full maturity.
        minimum_sample = max(
            1,
            int(self.policy["thresholds"]["minimum_outcome_sample"]),
        )
        sample_maturity = min(1.0, len(rows) / minimum_sample)
        reliability = base_reliability * sample_maturity

        recent_window = int(self.policy["thresholds"]["recent_outcome_window"])
        recent = rows[-recent_window:]
        prior = rows[:-recent_window]

        recent_success = sum(
            row["outcome"] == "Successful" for row in recent
        ) / len(recent)
        recent_recurrence = sum(
            bool(row["recurrence_within_24h"]) for row in recent
        ) / len(recent)

        if prior:
            prior_success = sum(
                row["outcome"] == "Successful" for row in prior
            ) / len(prior)
            prior_recurrence = sum(
                bool(row["recurrence_within_24h"]) for row in prior
            ) / len(prior)
        else:
            prior_success = recent_success
            prior_recurrence = recent_recurrence

        success_drop = prior_success - recent_success
        recurrence_increase = recent_recurrence - prior_recurrence
        drift_reasons: list[str] = []

        if success_drop >= float(self.policy["thresholds"]["drift_success_drop"]):
            drift_reasons.append("RECENT_SUCCESS_RATE_DECLINE")
        if recurrence_increase >= float(
            self.policy["thresholds"]["drift_recurrence_increase"]
        ):
            drift_reasons.append("RECENT_RECURRENCE_INCREASE")

        if drift_reasons:
            drift_status = "ERODING"
        elif recent_success > prior_success + 0.10 and recent_recurrence < prior_recurrence:
            drift_status = "IMPROVING"
        else:
            drift_status = "STABLE"

        return OutcomeProfile(
            sample_size=len(rows),
            sample_maturity=round(sample_maturity, 3),
            weighted_success_rate=round(weighted_success, 3),
            weighted_recurrence_rate=round(weighted_recurrence, 3),
            weighted_evidence_usefulness=round(weighted_usefulness, 3),
            weighted_prior_confidence=round(weighted_prior_confidence, 3),
            recent_success_rate=round(recent_success, 3),
            recent_recurrence_rate=round(recent_recurrence, 3),
            prior_success_rate=round(prior_success, 3),
            prior_recurrence_rate=round(prior_recurrence, 3),
            drift_status=drift_status,
            drift_reasons=drift_reasons,
            reliability_score=round(max(0.0, min(1.0, reliability)), 3),
        )

    def _governed_knowledge(
        self,
        *,
        known_error: dict,
        assessed_at: datetime,
    ) -> tuple[list[str], float]:
        maximum_age = int(
            self.policy["thresholds"]["knowledge_max_age_days"]
        )
        accepted = []
        for row in self.knowledge:
            entity_ids = {
                item.strip()
                for item in row.get("entity_ids", "").split(",")
                if item.strip()
            }
            symptoms = {
                item.strip()
                for item in row.get("symptom_categories", "").split(",")
                if item.strip()
            }
            relevant = (
                known_error["known_error_id"] in entity_ids
                or known_error["applies_to_entity_id"] in entity_ids
                or known_error["symptom_category"] in symptoms
            )
            if not relevant:
                continue
            if row.get("status") != "Published":
                continue
            if row.get("trust_level") != "Trusted":
                continue
            if row.get("content_safety_status") != "SAFE":
                continue
            validation_text = row.get("last_validated_at", "")
            if not validation_text:
                continue
            validated = datetime.strptime(validation_text, "%Y-%m-%d")
            if (assessed_at - validated).days > maximum_age:
                continue
            accepted.append(row["document_id"])

        readiness = min(1.0, len(accepted) / 2.0)
        return sorted(accepted), readiness

    def _recent_high_risk_changes(
        self,
        *,
        entity_id: str,
        assessed_at: datetime,
    ) -> list[dict]:
        lookback = float(
            self.policy["thresholds"]["high_risk_change_lookback_hours"]
        )

        # Evaluate changes across a bounded authoritative technical
        # neighborhood, not only the exact known-error entity.
        relevant_entities = {entity_id}
        frontier = [entity_id]
        for _ in range(2):
            next_frontier = []
            for node in frontier:
                for predicate, direction in (
                    ("FEEDS", "out"),
                    ("CALLS", "out"),
                    ("IMPLEMENTS", "out"),
                    ("DEPENDS_ON", "in"),
                ):
                    for step in self.graph.follow(
                        node,
                        predicate=predicate,
                        direction=direction,
                        minimum_confidence=0.75,
                        allowed_authorities={"AUTHORITATIVE"},
                    ):
                        if step.to_entity_id not in relevant_entities:
                            relevant_entities.add(step.to_entity_id)
                            next_frontier.append(step.to_entity_id)
            frontier = next_frontier

        result = []
        for row in self.changes:
            if row.get("entity_id") not in relevant_entities:
                continue
            implemented = self._dt(row["implemented_at"])
            age_hours = (
                assessed_at - implemented
            ).total_seconds() / 3600
            if (
                0 <= age_hours <= lookback
                and row.get("risk") == "High"
            ):
                result.append(row)
        return result

    @staticmethod
    def _trigger_support(known_error: dict, observation: dict) -> float:
        score = 0.0
        if known_error.get("trigger_metric_id") == observation.get("metric_id"):
            score += 0.65
        if observation.get("severity") == "CRITICAL":
            score += 0.25
        elif observation.get("severity") == "HIGH":
            score += 0.15
        if observation.get("threshold_breached"):
            score += 0.10
        return min(1.0, score)

    @staticmethod
    def to_dict(result: OperationalConfidenceAssessment) -> dict:
        return asdict(result)
