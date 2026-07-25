from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Iterable
import json
import math
import re

from graph_engine import SemanticGraph
from telemetry_agent import TelemetryAnalysisAgent


TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
FREE_TEXT_TYPES = {
    "KNOWLEDGE_ARTICLE",
    "RUNBOOK",
    "POST_INCIDENT_REVIEW",
    "BUSINESS_IMPACT_GUIDE",
    "CHANGE_IMPLEMENTATION_NOTE",
    "ENGINEERING_WIKI",
}
STRUCTURED_RECORD_TYPES = {"INCIDENT", "PROBLEM", "CHANGE"}
SUSPICIOUS_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+|previous\s+|formal\s+)?(?:instructions|approval)", re.I),
    re.compile(r"bypass\s+(?:approval|controls?|safety)", re.I),
    re.compile(r"disable\s+(?:controls?|safety|guardrails?)", re.I),
    re.compile(r"delete\s+retained\s+messages", re.I),
)
METRIC_SYMPTOMS = {
    "MET-PAY-TIMEOUT": {"PAYMENT_TIMEOUT"},
    "MET-CONN-ACTIVE": {"CONNECTOR_SATURATION"},
    "MET-DB-UTIL": {"DB_CONNECTION_SATURATION"},
    "MET-HTTP-5XX": {"HTTP_5XX"},
    "MET-P95-LATENCY": {"LATENCY"},
    "MET-QUEUE-DEPTH": {"QUEUE_BACKLOG"},
    "MET-CONSUMER-LAG": {"CONSUMER_LAG"},
    "MET-ACC-DELAY": {"CONSUMER_LAG"},
    "MET-FRAUD-DELAY": {"CONSUMER_LAG"},
    "MET-ALERT-COUNT": {"ALERT_STORM"},
    "MET-GIT-AUTH-FAIL": {"SAAS_ACCESS_FAILURE"},
    "MET-TEAMS-JOIN-FAIL": {"SAAS_ACCESS_FAILURE"},
    "MET-GW-TLS-HANDSHAKE-FAIL": {"GATEWAY_SESSION_DISRUPTION"},
}
SOURCE_WEIGHTS = {
    "KNOWLEDGE_ARTICLE": 2.0,
    "RUNBOOK": 1.8,
    "POST_INCIDENT_REVIEW": 1.7,
    "BUSINESS_IMPACT_GUIDE": 1.5,
    "CHANGE_IMPLEMENTATION_NOTE": 1.4,
    "PROBLEM": 1.3,
    "CHANGE": 1.1,
    "INCIDENT": 1.0,
    "ENGINEERING_WIKI": 0.5,
}


@dataclass(frozen=True)
class RetrievalCandidate:
    chunk_id: str
    source_id: str
    source_type: str
    evidence_class: str
    title: str
    text: str
    score: float
    entity_overlap: list[str]
    symptom_overlap: list[str]
    lexical_overlap: list[str]
    trust_level: str
    content_safety_status: str
    governance_decision: str
    rejection_reasons: list[str]
    limitation_reasons: list[str]
    material_contradiction: bool
    contradicts_known_error_ids: list[str]
    alternative_hypothesis_id: str | None
    corroboration_count: int
    enterprise_approved: bool | None
    provenance: str


@dataclass(frozen=True)
class RetrievalAssessment:
    scenario_id: str
    scenario_name: str
    trigger_observation_id: str
    trigger_observed_at: str
    query_text: str
    graph_context_entity_ids: list[str]
    authoritative_entity_ids: list[str]
    hypothesis_entity_ids: list[str]
    symptom_categories: list[str]
    accepted_free_text: list[RetrievalCandidate]
    accepted_with_limitations: list[RetrievalCandidate]
    accepted_structured_records: list[RetrievalCandidate]
    rejected_candidates: list[RetrievalCandidate]
    retrieval_explanation: str


class KnowledgeRetrievalAgent:
    """Graph-constrained, governance-aware deterministic RAG retriever.

    This is the retrieval/control-plane baseline. A vector or hybrid semantic
    scorer can later replace lexical scoring without weakening the governance
    contract or evidence separation.
    """

    def __init__(self, json_dir: str | Path) -> None:
        self.json_dir = Path(json_dir)
        self.graph = SemanticGraph.from_json_directory(self.json_dir)
        self.telemetry = TelemetryAnalysisAgent(self.json_dir)
        self.scenarios = self._load_json("scenarios.json")
        self.observations = self._load_json("health_observations.json")
        self.knowledge_documents = self._load_json("knowledge_documents.json")
        self.incidents = self._load_json("incidents.json")
        self.problems = self._load_json("problems.json")
        self.changes = self._load_json("changes.json")
        self.corpus = self._load_jsonl("rag_corpus.jsonl")

        self.scenario_by_id = {r["scenario_id"]: r for r in self.scenarios}
        self.observation_by_id = {r["observation_id"]: r for r in self.observations}
        self.doc_by_id = {r["document_id"]: r for r in self.knowledge_documents}
        self.structured_availability = self._build_structured_availability()

    def _load_json(self, filename: str) -> list[dict]:
        with open(self.json_dir / filename, encoding="utf-8") as f:
            return json.load(f)

    def _load_jsonl(self, filename: str) -> list[dict]:
        with open(self.json_dir / filename, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def _build_structured_availability(self) -> dict[str, datetime]:
        result: dict[str, datetime] = {}
        for row in self.incidents:
            result[row["incident_id"]] = self._parse_datetime(row["opened_at"])
        for row in self.problems:
            result[row["problem_id"]] = self._parse_datetime(row["opened_at"])
        for row in self.changes:
            result[row["change_id"]] = self._parse_datetime(row["implemented_at"])
        return result

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _parse_date(value: str) -> date | None:
        if not value:
            return None
        return datetime.strptime(value, "%Y-%m-%d").date()

    @staticmethod
    def _tokens(text: str) -> set[str]:
        stop = {
            "the", "and", "for", "with", "from", "this", "that", "into",
            "after", "before", "during", "when", "then", "than", "are",
            "was", "were", "has", "have", "had", "not", "but", "can",
            "may", "must", "should", "will", "its", "our", "their", "a",
            "an", "of", "to", "in", "on", "at", "by", "or", "is", "be",
        }
        return {
            token.lower() for token in TOKEN_RE.findall(text)
            if len(token) >= 3 and token.lower() not in stop
        }

    @staticmethod
    def _contains_suspicious_instruction(text: str) -> bool:
        """Detect unsafe imperatives while avoiding false positives in prohibitions."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for sentence in sentences:
            lowered = sentence.lower()
            if any(marker in lowered for marker in ("do not", "must not", "never")):
                continue
            if any(pattern.search(sentence) for pattern in SUSPICIOUS_PATTERNS):
                return True
        return False

    def _graph_context(self, scenario: dict, trigger: dict, telemetry):
        """Build a bounded semantic neighborhood without crossing unrelated branches.

        Traversal follows domain-valid directions rather than unconstrained
        undirected breadth-first search. Hypothesis paths retain inferred status.
        """
        telemetry_entities = {
            summary.entity_id for summary in telemetry.metric_summaries
            if summary.current_status in {"HIGH", "CRITICAL"}
        }
        focal = {
            trigger["observation_id"],
            trigger["entity_id"],
            scenario["primary_component_id"],
            scenario["primary_service_id"],
            *telemetry_entities,
        }
        authoritative = set(focal)
        hypotheses: set[str] = set()

        def add_out(source: str, predicates: set[str], *, hypothesis: bool = False):
            if source not in self.graph.entities:
                return []
            steps = list(self.graph.iter_neighbors(
                source,
                direction="out",
                predicates=predicates,
                minimum_confidence=0.75,
                allowed_authorities={"AUTHORITATIVE", "OBSERVED"},
            ))
            for step in steps:
                (hypotheses if hypothesis else authoritative).add(step.to_entity_id)
            return steps

        def add_in(source: str, predicates: set[str], *, hypothesis: bool = False):
            if source not in self.graph.entities:
                return []
            steps = list(self.graph.iter_neighbors(
                source,
                direction="in",
                predicates=predicates,
                minimum_confidence=0.75,
                allowed_authorities={"AUTHORITATIVE", "OBSERVED"},
            ))
            for step in steps:
                (hypotheses if hypothesis else authoritative).add(step.to_entity_id)
            return steps

        # Observation semantics and directly applicable known errors.
        observed_steps = add_out(trigger["observation_id"], {"OBSERVES"})
        observed_components = {step.to_entity_id for step in observed_steps}
        for component in observed_components | {scenario["primary_component_id"]}:
            known_error_steps = add_in(component, {"APPLIES_TO"})
            for step in known_error_steps:
                add_in(step.to_entity_id, {"DESCRIBES"})

        # Only dependencies corroborated by this scenario's telemetry are added.
        primary_service = scenario["primary_service_id"]
        for step in self.graph.iter_neighbors(
            primary_service,
            direction="out",
            predicates={"DEPENDS_ON"},
            allowed_authorities={"AUTHORITATIVE"},
        ):
            if step.to_entity_id in telemetry_entities or step.to_entity_id in observed_components:
                authoritative.add(step.to_entity_id)

        # Technical downstream path from the focal component.
        frontier = list(observed_components | {scenario["primary_component_id"]})
        visited = set(frontier)
        for _ in range(3):
            next_frontier = []
            for node in frontier:
                for step in self.graph.iter_neighbors(
                    node,
                    direction="out",
                    predicates={"CALLS", "FEEDS", "IMPLEMENTS"},
                    allowed_authorities={"AUTHORITATIVE"},
                ):
                    authoritative.add(step.to_entity_id)
                    if step.to_entity_id not in visited:
                        visited.add(step.to_entity_id)
                        next_frontier.append(step.to_entity_id)
            frontier = next_frontier

        # Business impact path from the primary service and affected downstream services.
        business_services = set()
        for service in {primary_service, *telemetry_entities, *authoritative}:
            if service not in self.graph.entities:
                continue
            for step in self.graph.iter_neighbors(
                service,
                direction="out",
                predicates={"SUPPORTS"},
                allowed_authorities={"AUTHORITATIVE"},
            ):
                authoritative.add(step.to_entity_id)
                business_services.add(step.to_entity_id)

        capabilities = set()
        for node in list(authoritative):
            if node not in self.graph.entities:
                continue
            for step in self.graph.iter_neighbors(
                node,
                direction="out",
                predicates={"ENABLES"},
                allowed_authorities={"AUTHORITATIVE"},
            ):
                authoritative.add(step.to_entity_id)
                capabilities.add(step.to_entity_id)
        for capability in capabilities:
            add_out(capability, {"CONTRIBUTES_TO"})

        # Inferred relationships are hypothesis context. Their descendants remain hypotheses.
        if trigger["observation_id"] in self.graph.entities:
            inferred_steps = list(self.graph.iter_neighbors(
                trigger["observation_id"],
                direction="in",
                predicates={"MAY_CONTRIBUTE_TO", "EXPLAINS"},
                minimum_confidence=0.75,
                allowed_authorities={"INFERRED"},
            ))
            for step in inferred_steps:
                hypotheses.add(step.to_entity_id)
                for child in self.graph.iter_neighbors(
                    step.to_entity_id,
                    direction="out",
                    predicates={"MODIFIES", "APPLIES_TO"},
                    allowed_authorities={"AUTHORITATIVE"},
                ):
                    hypotheses.add(child.to_entity_id)

        hypotheses -= authoritative
        all_entities = authoritative | hypotheses
        return (
            sorted(all_entities),
            sorted(authoritative),
            sorted(hypotheses),
            sorted(focal),
        )

    def retrieve(self, scenario_id: str, *, top_free_text: int = 6,
                 top_structured: int = 8) -> RetrievalAssessment:
        try:
            scenario = self.scenario_by_id[scenario_id]
        except KeyError as exc:
            raise KeyError(f"Unknown scenario: {scenario_id}") from exc

        trigger = self.observation_by_id[scenario["trigger_observation_id"]]
        trigger_dt = self._parse_datetime(trigger["observed_at"])
        telemetry = self.telemetry.analyze(scenario_id)
        graph_ids, authoritative_ids, hypothesis_ids, focal_ids = self._graph_context(
            scenario, trigger, telemetry
        )

        symptoms: set[str] = set()
        for summary in telemetry.metric_summaries:
            if summary.current_status in {"HIGH", "CRITICAL"}:
                symptoms.update(METRIC_SYMPTOMS.get(summary.metric_id, set()))

        graph_names = [
            self.graph.get_entity(entity_id).name
            for entity_id in graph_ids
            if entity_id in self.graph.entities
        ]
        query_text = " ".join([
            scenario["name"], scenario["description"],
            trigger["observation_summary"], telemetry.temporal_explanation,
            " ".join(graph_names), " ".join(sorted(symptoms)),
        ])
        query_tokens = self._tokens(query_text)

        accepted_free: list[RetrievalCandidate] = []
        accepted_limited: list[RetrievalCandidate] = []
        accepted_structured: list[RetrievalCandidate] = []
        rejected: list[RetrievalCandidate] = []

        for chunk in self.corpus:
            candidate = self._evaluate_candidate(
                chunk=chunk,
                trigger_dt=trigger_dt,
                graph_ids=set(graph_ids),
                authoritative_ids=set(authoritative_ids),
                hypothesis_ids=set(hypothesis_ids),
                focal_ids=set(focal_ids),
                symptoms=symptoms,
                query_tokens=query_tokens,
            )
            if candidate.governance_decision == "REJECTED":
                rejected.append(candidate)
            elif candidate.governance_decision == "ACCEPTED_WITH_LIMITATIONS":
                accepted_limited.append(candidate)
            elif candidate.evidence_class == "FREE_TEXT_KNOWLEDGE":
                accepted_free.append(candidate)
            else:
                accepted_structured.append(candidate)

        accepted_free.sort(key=lambda c: (-c.score, c.source_id))
        accepted_limited.sort(key=lambda c: (-c.score, c.source_id))
        accepted_structured.sort(key=lambda c: (-c.score, c.source_id))
        rejected.sort(key=lambda c: (-c.score, c.source_id))

        accepted_free = accepted_free[:top_free_text]
        accepted_limited = accepted_limited[:top_free_text]
        accepted_structured = accepted_structured[:top_structured]

        explanation = (
            f"Retrieved evidence for {scenario['name']} using graph entity overlap, "
            f"telemetry-derived symptom categories, and lexical relevance. "
            f"Free-text knowledge was separated into accepted, accepted with "
            f"limitations, and rejected evidence using publication, trust, safety, "
            f"staleness, enterprise-approval, contradiction, and corroboration checks. "
            f"Structured incidents, problems, and changes were treated as "
            f"approved-provenance records and filtered by availability at the "
            f"{trigger['observed_at']} trigger time. Inferred graph context was "
            f"retained as hypothesis context, not authoritative fact."
        )

        return RetrievalAssessment(
            scenario_id=scenario_id,
            scenario_name=scenario["name"],
            trigger_observation_id=trigger["observation_id"],
            trigger_observed_at=trigger["observed_at"],
            query_text=query_text,
            graph_context_entity_ids=graph_ids,
            authoritative_entity_ids=authoritative_ids,
            hypothesis_entity_ids=hypothesis_ids,
            symptom_categories=sorted(symptoms),
            accepted_free_text=accepted_free,
            accepted_with_limitations=accepted_limited,
            accepted_structured_records=accepted_structured,
            rejected_candidates=rejected,
            retrieval_explanation=explanation,
        )

    def _evaluate_candidate(
        self, *, chunk: dict, trigger_dt: datetime, graph_ids: set[str],
        authoritative_ids: set[str], hypothesis_ids: set[str],
        focal_ids: set[str], symptoms: set[str], query_tokens: set[str],
    ) -> RetrievalCandidate:
        source_type = chunk["source_type"]
        evidence_class = (
            "STRUCTURED_ENTERPRISE_RECORD"
            if source_type in STRUCTURED_RECORD_TYPES
            else "FREE_TEXT_KNOWLEDGE"
        )
        candidate_entities = set(chunk.get("entity_ids", []))
        candidate_symptoms = set(chunk.get("symptom_categories", []))
        entity_overlap = candidate_entities & graph_ids
        focal_overlap = candidate_entities & focal_ids
        authoritative_overlap = candidate_entities & authoritative_ids
        hypothesis_overlap = candidate_entities & hypothesis_ids
        symptom_overlap = candidate_symptoms & symptoms

        candidate_tokens = self._tokens(
            f"{chunk.get('title', '')} {chunk.get('text', '')}"
        )
        lexical_overlap = candidate_tokens & query_tokens
        lexical_score = len(lexical_overlap) / math.sqrt(max(len(candidate_tokens), 1))

        score = SOURCE_WEIGHTS.get(source_type, 0.5)
        score += 6.0 * len(focal_overlap)
        score += 2.0 * len(authoritative_overlap - focal_overlap)
        score += 1.25 * len(hypothesis_overlap)
        score += 3.5 * len(symptom_overlap)
        score += 2.0 * lexical_score

        rejection_reasons: list[str] = []
        limitation_reasons: list[str] = []
        suspicious = self._contains_suspicious_instruction(chunk.get("text", ""))

        # Relevance gate: graph-constrained or symptom-constrained, not corpus-wide similarity.
        if not entity_overlap and not symptom_overlap:
            rejection_reasons.append("OUTSIDE_GRAPH_AND_SYMPTOM_CONTEXT")

        if evidence_class == "FREE_TEXT_KNOWLEDGE":
            doc = self.doc_by_id.get(chunk["source_id"])
            if doc and doc.get("status") != "Published":
                rejection_reasons.append(
                    f"DOCUMENT_STATUS_{doc.get('status', 'UNKNOWN').upper()}"
                )

            trust_level = chunk.get("trust_level", "UNKNOWN")
            if trust_level == "Conditional":
                limitation_reasons.append("TRUST_CONDITIONAL")
            elif trust_level != "Trusted":
                rejection_reasons.append(f"TRUST_{trust_level.upper()}")

            if chunk.get("content_safety_status") != "SAFE":
                rejection_reasons.append(
                    f"CONTENT_SAFETY_{chunk.get('content_safety_status', 'UNKNOWN')}"
                )
            if suspicious:
                rejection_reasons.append("SUSPICIOUS_INSTRUCTION_PATTERN")

            validated = self._parse_date(chunk.get("last_validated_at", ""))
            if validated is None:
                rejection_reasons.append("MISSING_VALIDATION_DATE")
            elif (trigger_dt.date() - validated).days > 180:
                rejection_reasons.append("STALE_OVER_180_DAYS")

            published = self._parse_date(chunk.get("published_at", ""))
            if published and published > trigger_dt.date():
                rejection_reasons.append("PUBLISHED_AFTER_TRIGGER")

            if chunk.get("enterprise_approved") is False:
                limitation_reasons.append("NOT_ENTERPRISE_APPROVED")
            if chunk.get("material_contradiction"):
                limitation_reasons.append("MATERIAL_CONTRADICTION")
                if int(chunk.get("corroboration_count", 0)) == 0:
                    limitation_reasons.append("NO_INDEPENDENT_CORROBORATION")
        else:
            available_at = self.structured_availability.get(chunk["source_id"])
            if available_at is None:
                rejection_reasons.append("MISSING_STRUCTURED_PROVENANCE_TIME")
            elif available_at > trigger_dt:
                rejection_reasons.append("STRUCTURED_RECORD_NOT_YET_AVAILABLE")

        if rejection_reasons:
            decision = "REJECTED"
        elif limitation_reasons:
            decision = "ACCEPTED_WITH_LIMITATIONS"
        else:
            decision = "ACCEPTED"
        provenance = (
            "Approved structured enterprise record with source timestamp"
            if evidence_class == "STRUCTURED_ENTERPRISE_RECORD"
            else "Governed free-text corpus with publication, validation, trust, and safety metadata"
        )

        return RetrievalCandidate(
            chunk_id=chunk["chunk_id"],
            source_id=chunk["source_id"],
            source_type=source_type,
            evidence_class=evidence_class,
            title=chunk["title"],
            text=chunk["text"],
            score=round(score, 3),
            entity_overlap=sorted(entity_overlap),
            symptom_overlap=sorted(symptom_overlap),
            lexical_overlap=sorted(lexical_overlap)[:20],
            trust_level=chunk.get("trust_level", ""),
            content_safety_status=chunk.get("content_safety_status", ""),
            governance_decision=decision,
            rejection_reasons=rejection_reasons,
            limitation_reasons=limitation_reasons,
            material_contradiction=bool(chunk.get("material_contradiction", False)),
            contradicts_known_error_ids=list(
                chunk.get("contradicts_known_error_ids", [])
            ),
            alternative_hypothesis_id=chunk.get("alternative_hypothesis_id"),
            corroboration_count=int(chunk.get("corroboration_count", 0)),
            enterprise_approved=chunk.get("enterprise_approved"),
            provenance=provenance,
        )

    @staticmethod
    def to_dict(result: RetrievalAssessment) -> dict:
        return asdict(result)
