from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json

from graph_engine import SemanticGraph, PathStep


@dataclass(frozen=True)
class GraphFact:
    relationship_id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str
    authority: str
    confidence: float
    provenance: str
    reasoning_role: str


@dataclass(frozen=True)
class GraphContextAssessment:
    scenario_id: str
    scenario_name: str
    trigger_observation_id: str
    primary_component_id: str
    primary_service_id: str
    authoritative_entity_ids: list[str]
    hypothesis_entity_ids: list[str]
    impacted_capability_ids: list[str]
    business_outcome_ids: list[str]
    facts: list[GraphFact]
    explanation: str


class GraphContextAgent:
    """Build a bounded semantic neighborhood around the trigger.

    Authoritative and observed edges become context facts. Inferred edges are
    retained separately as hypotheses and never promoted to facts.
    """

    def __init__(self, json_dir: str | Path) -> None:
        self.json_dir = Path(json_dir)
        self.graph = SemanticGraph.from_json_directory(self.json_dir)
        self.scenarios = self._load("scenarios.json")
        self.scenario_by_id = {row["scenario_id"]: row for row in self.scenarios}

    def _load(self, filename: str) -> list[dict]:
        with open(self.json_dir / filename, encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _fact(step: PathStep, role: str) -> GraphFact:
        relationship = step.relationship
        return GraphFact(
            relationship_id=relationship.relationship_id,
            subject_entity_id=relationship.subject_entity_id,
            predicate=relationship.predicate,
            object_entity_id=relationship.object_entity_id,
            authority=relationship.authority,
            confidence=relationship.confidence,
            provenance=relationship.provenance,
            reasoning_role=role,
        )

    def analyze(self, scenario_id: str) -> GraphContextAssessment:
        try:
            scenario = self.scenario_by_id[scenario_id]
        except KeyError as exc:
            raise KeyError(f"Unknown scenario: {scenario_id}") from exc

        trigger_id = scenario["trigger_observation_id"]
        primary_component = scenario["primary_component_id"]
        primary_service = scenario["primary_service_id"]

        authoritative = {
            trigger_id,
            primary_component,
            primary_service,
        }
        hypotheses: set[str] = set()
        facts: dict[str, GraphFact] = {}

        def add_steps(steps: list[PathStep], role: str, *, hypothesis: bool = False) -> list[PathStep]:
            for step in steps:
                facts.setdefault(step.relationship.relationship_id, self._fact(step, role))
                target_set = hypotheses if hypothesis else authoritative
                target_set.add(step.from_entity_id)
                target_set.add(step.to_entity_id)
            return steps

        observed = add_steps(
            self.graph.follow(
                trigger_id,
                predicate="OBSERVES",
                direction="out",
                minimum_confidence=0.75,
                allowed_authorities={"OBSERVED"},
            ),
            "TRIGGER_CONTEXT",
        )
        observed_components = {step.to_entity_id for step in observed}
        focal_components = observed_components | {primary_component}

        # Known-error applicability and technical dependency context.
        for component in focal_components:
            add_steps(
                self.graph.follow(
                    component,
                    predicate="APPLIES_TO",
                    direction="in",
                    minimum_confidence=0.75,
                    allowed_authorities={"AUTHORITATIVE"},
                ),
                "KNOWN_ERROR_APPLICABILITY",
            )
            add_steps(
                self.graph.follow(
                    component,
                    predicate="DEPENDS_ON",
                    direction="in",
                    minimum_confidence=0.75,
                    allowed_authorities={"AUTHORITATIVE"},
                ),
                "UPSTREAM_DEPENDENCY",
            )

        # Outbound technical blast radius: CALLS and FEEDS, then IMPLEMENTS.
        frontier = list(focal_components)
        visited = set(frontier)
        for _ in range(3):
            next_frontier: list[str] = []
            for node in frontier:
                for predicate in ("CALLS", "FEEDS", "IMPLEMENTS"):
                    steps = add_steps(
                        self.graph.follow(
                            node,
                            predicate=predicate,
                            direction="out",
                            minimum_confidence=0.75,
                            allowed_authorities={"AUTHORITATIVE"},
                        ),
                        "TECHNICAL_BLAST_RADIUS",
                    )
                    for step in steps:
                        if step.to_entity_id not in visited:
                            visited.add(step.to_entity_id)
                            next_frontier.append(step.to_entity_id)
            frontier = next_frontier

        # Business paths from the primary and discovered services/components.
        business_services: set[str] = set()
        for node in list(authoritative):
            if node not in self.graph.entities:
                continue
            for predicate in ("SUPPORTS",):
                steps = add_steps(
                    self.graph.follow(
                        node,
                        predicate=predicate,
                        direction="out",
                        minimum_confidence=0.75,
                        allowed_authorities={"AUTHORITATIVE"},
                    ),
                    "BUSINESS_SERVICE_IMPACT",
                )
                business_services.update(step.to_entity_id for step in steps)

        capabilities: set[str] = set()
        for node in list(authoritative):
            if node not in self.graph.entities:
                continue
            steps = add_steps(
                self.graph.follow(
                    node,
                    predicate="ENABLES",
                    direction="out",
                    minimum_confidence=0.75,
                    allowed_authorities={"AUTHORITATIVE"},
                ),
                "CAPABILITY_IMPACT",
            )
            capabilities.update(step.to_entity_id for step in steps)

        outcomes: set[str] = set()
        for capability in capabilities:
            steps = add_steps(
                self.graph.follow(
                    capability,
                    predicate="CONTRIBUTES_TO",
                    direction="out",
                    minimum_confidence=0.75,
                    allowed_authorities={"AUTHORITATIVE"},
                ),
                "BUSINESS_OUTCOME_IMPACT",
            )
            outcomes.update(step.to_entity_id for step in steps)

        # Inferred contributors remain hypotheses.
        for predicate in ("MAY_CONTRIBUTE_TO", "EXPLAINS"):
            inferred = self.graph.follow(
                trigger_id,
                predicate=predicate,
                direction="in",
                minimum_confidence=0.70,
                allowed_authorities={"INFERRED"},
            )
            add_steps(inferred, "CAUSAL_HYPOTHESIS", hypothesis=True)

        hypotheses -= authoritative

        explanation = (
            f"Built a bounded graph context for {scenario['name']}. "
            f"{len(authoritative)} entities were reached through observed or "
            f"authoritative relationships. {len(hypotheses)} entities were retained "
            f"only as inferred hypothesis context. The graph identified "
            f"{len(capabilities)} impacted capabilities and {len(outcomes)} "
            f"business outcomes."
        )

        return GraphContextAssessment(
            scenario_id=scenario_id,
            scenario_name=scenario["name"],
            trigger_observation_id=trigger_id,
            primary_component_id=primary_component,
            primary_service_id=primary_service,
            authoritative_entity_ids=sorted(authoritative),
            hypothesis_entity_ids=sorted(hypotheses),
            impacted_capability_ids=sorted(capabilities),
            business_outcome_ids=sorted(outcomes),
            facts=sorted(facts.values(), key=lambda item: item.relationship_id),
            explanation=explanation,
        )

    @staticmethod
    def to_dict(result: GraphContextAssessment) -> dict:
        return asdict(result)
