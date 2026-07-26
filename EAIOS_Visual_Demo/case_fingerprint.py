from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json

from graph_engine import SemanticGraph


# Edges that describe what a component sits on. Used to place an entity in the
# dependency graph without caring what the entity is called.
STRUCTURAL_PREDICATES = {"DEPENDS_ON", "ROUTED_THROUGH", "HOSTED_ON", "CALLS", "FEEDS"}


@dataclass(frozen=True)
class CaseFingerprint:
    """What a case looks like, independent of what it is called.

    Experience is currently retrieved by known-error identifier, which means a
    pattern resolved fifty times on one component transfers nothing to a
    structurally identical sibling. A fingerprint describes the presentation
    instead: what kind of thing is failing, where it sits, what is breaching
    and how hard, and how far the effect reaches. Two cases can then be
    compared without either of them having a diagnosis yet.

    This is also the compact form the architecture calls pattern memory: small
    enough to hold for every case, sufficient to decide whether pulling the
    full record is justified.
    """

    entity_id: str
    entity_type: str
    service_provider_type: str
    # Structural position: what this entity rests on, and what rests on it.
    depends_on: tuple[str, ...] = ()
    depended_on_by: tuple[str, ...] = ()
    parent_services: tuple[str, ...] = ()
    # Presentation: which metrics are breaching and how severely.
    breaching_metrics: tuple[str, ...] = ()
    symptom_categories: tuple[str, ...] = ()
    severity_band: str = "NONE"
    # Reach: how far the effect extends into the business.
    impacted_capabilities: tuple[str, ...] = ()
    blast_radius: int = 0
    # Patterns the enterprise has explicitly declared relevant to this entity
    # or its bounded neighbourhood. Curated expert knowledge, not inference.
    declared_patterns: tuple[str, ...] = ()
    # For a remembered pattern: every entity an expert declared it covers, not
    # only the one it is filed under.
    covered_entities: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return asdict(self)


def severity_band(observed: float, threshold: float, higher_is_worse: bool) -> str:
    """Coarse magnitude, so near-identical cases band together.

    Exact values never repeat; bands do. Comparing bands is what lets two
    presentations of the same shape recognise each other.
    """
    if threshold in (None, 0):
        return "UNKNOWN"
    ratio = observed / threshold if higher_is_worse else threshold / max(observed, 1e-9)
    if ratio < 1.0:
        return "WITHIN_THRESHOLD"
    if ratio < 1.5:
        return "MARGINAL"
    if ratio < 3.0:
        return "SEVERE"
    return "EXTREME"


class CaseFingerprinter:
    """Build fingerprints from the graph and the observation record."""

    def __init__(self, json_dir: str | Path) -> None:
        self.json_dir = Path(json_dir)
        self.graph = SemanticGraph.from_json_directory(self.json_dir)
        self.observations = self._load("health_observations.json")
        self.metrics = {
            row["metric_id"]: row for row in self._load("metric_definitions.json")
        }
        self.scenarios = {
            row["scenario_id"]: row for row in self._load("scenarios.json")
        }
        self.observation_by_id = {
            row["observation_id"]: row for row in self.observations
        }

    def _load(self, filename: str) -> list[dict]:
        return json.loads((self.json_dir / filename).read_text(encoding="utf-8"))

    def _neighbours(self, entity_id: str, direction: str) -> tuple[str, ...]:
        if entity_id not in self.graph.entities:
            return ()
        found = self.graph.reachable_paths(
            entity_id,
            max_hops=1,
            direction=direction,
            predicates=STRUCTURAL_PREDICATES,
            allowed_authorities={"AUTHORITATIVE"},
        )
        return tuple(sorted(found))

    def _capabilities(self, entity_id: str) -> tuple[str, ...]:
        """Business capabilities the entity ultimately serves."""
        if entity_id not in self.graph.entities:
            return ()
        reachable = self.graph.reachable_paths(
            entity_id,
            max_hops=4,
            direction="both",
            predicates={"DEPENDS_ON", "SUPPORTS", "ENABLES", "ROUTED_THROUGH"},
            allowed_authorities={"AUTHORITATIVE"},
        )
        return tuple(
            sorted(
                entity
                for entity in reachable
                if self.graph.get_entity(entity).entity_type == "BUSINESS_CAPABILITY"
            )
        )

    def _declared_patterns(self, entity_id: str) -> tuple[str, ...]:
        """Patterns an expert has declared relevant here or next door.

        An APPLIES_TO edge is the enterprise stating that a recorded pattern
        affects a component. That is knowledge similarity cannot infer, and
        discarding it in favour of pure resemblance loses curation.
        """
        if entity_id not in self.graph.entities:
            return ()
        scope = {entity_id}
        for predicate, direction in (
            ("DEPENDS_ON", "in"), ("CALLS", "out"),
            ("FEEDS", "out"), ("IMPLEMENTS", "out"),
        ):
            for step in self.graph.follow(
                entity_id, predicate=predicate, direction=direction,
                minimum_confidence=0.75, allowed_authorities={"AUTHORITATIVE"},
            ):
                scope.add(step.to_entity_id)

        declared = set()
        for node in scope:
            for step in self.graph.follow(
                node, predicate="APPLIES_TO", direction="in",
                minimum_confidence=0.75, allowed_authorities={"AUTHORITATIVE"},
            ):
                declared.add(step.to_entity_id)
        return tuple(sorted(declared))

    def for_observation(self, observation: dict) -> CaseFingerprint:
        entity_id = observation["entity_id"]
        entity = (
            self.graph.get_entity(entity_id)
            if entity_id in self.graph.entities
            else None
        )
        attributes = entity.attributes if entity else {}

        metric_id = observation.get("metric_id", "")
        metric = self.metrics.get(metric_id, {})
        band = severity_band(
            float(observation.get("current_value", 0.0)),
            float(observation.get("threshold_value", 0.0) or 0.0),
            bool(metric.get("higher_is_worse", True)),
        )
        capabilities = self._capabilities(entity_id)

        return CaseFingerprint(
            entity_id=entity_id,
            entity_type=attributes.get("entity_type", ""),
            service_provider_type=attributes.get("service_provider_type", "INTERNAL"),
            depends_on=self._neighbours(entity_id, "out"),
            depended_on_by=self._neighbours(entity_id, "in"),
            parent_services=tuple(
                sorted(
                    e
                    for e in self._neighbours(entity_id, "in")
                    if self.graph.get_entity(e).entity_type
                    in {"APPLICATION_SERVICE", "BUSINESS_SERVICE"}
                )
            ),
            breaching_metrics=(metric_id,) if metric_id else (),
            symptom_categories=tuple(
                sorted(metric.get("symptom_categories", []) or [])
            ),
            severity_band=band,
            impacted_capabilities=capabilities,
            blast_radius=len(capabilities),
            declared_patterns=self._declared_patterns(entity_id),
        )

    def for_scenario(self, scenario_id: str) -> CaseFingerprint:
        scenario = self.scenarios[scenario_id]
        return self.for_observation(
            self.observation_by_id[scenario["trigger_observation_id"]]
        )

    def for_known_error(self, known_error: dict) -> CaseFingerprint:
        """The presentation a recorded pattern describes.

        Built from the pattern's own entity and trigger metric so a known
        error can be compared against a live case on equal terms.
        """
        entity_id = known_error["applies_to_entity_id"]
        metric_id = known_error.get("trigger_metric_id", "")
        synthetic_observation = {
            "entity_id": entity_id,
            "metric_id": metric_id,
            "current_value": 0.0,
            "threshold_value": 0.0,
        }
        fingerprint = self.for_observation(synthetic_observation)
        # A pattern may present differently depending on where it surfaces, so
        # it may declare more than one symptom vocabulary.
        declared = set(known_error.get("symptom_categories", []) or [])
        if known_error.get("symptom_category"):
            declared.add(known_error["symptom_category"])
        covered = {entity_id}
        for step in self.graph.follow(
            known_error["known_error_id"], predicate="APPLIES_TO", direction="out",
            minimum_confidence=0.75, allowed_authorities={"AUTHORITATIVE"},
        ) if known_error["known_error_id"] in self.graph.entities else []:
            covered.add(step.to_entity_id)

        return CaseFingerprint(**{
            **fingerprint.as_dict(),
            "symptom_categories": tuple(
                sorted(set(fingerprint.symptom_categories) | declared)
            ),
            "declared_patterns": (known_error["known_error_id"],),
            "covered_entities": tuple(sorted(covered)),
        })
