from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Literal
import json

Direction = Literal["out", "in", "both"]

@dataclass(frozen=True)
class Entity:
    entity_id: str
    entity_type: str
    name: str
    attributes: dict

@dataclass(frozen=True)
class Relationship:
    relationship_id: str
    subject_entity_id: str
    predicate: str
    object_entity_id: str
    authority: str
    confidence: float
    provenance: str
    attributes: dict

@dataclass(frozen=True)
class PathStep:
    from_entity_id: str
    relationship: Relationship
    to_entity_id: str
    traversal_direction: Literal["out", "in"]

class SemanticGraph:
    """Small, dependency-free semantic graph for the Hybrid EAIOS demo."""

    def __init__(self, entities: Iterable[dict], relationships: Iterable[dict]) -> None:
        self.entities: dict[str, Entity] = {}
        self.relationships: dict[str, Relationship] = {}
        self._out: dict[str, list[Relationship]] = {}
        self._in: dict[str, list[Relationship]] = {}

        for row in entities:
            entity_id = str(row["entity_id"]).strip()
            if not entity_id:
                raise ValueError("Entity ID cannot be blank.")
            self.entities[entity_id] = Entity(
                entity_id=entity_id,
                entity_type=str(row.get("entity_type", "")).strip(),
                name=str(row.get("name", entity_id)).strip(),
                attributes=dict(row),
            )

        for row in relationships:
            rel = Relationship(
                relationship_id=str(row["relationship_id"]).strip(),
                subject_entity_id=str(row["subject_entity_id"]).strip(),
                predicate=str(row["predicate"]).strip(),
                object_entity_id=str(row["object_entity_id"]).strip(),
                authority=str(row.get("relationship_authority", "")).strip(),
                confidence=float(row.get("confidence", 0.0)),
                provenance=str(row.get("provenance", "")).strip(),
                attributes=dict(row),
            )
            if rel.subject_entity_id not in self.entities:
                raise ValueError(f"{rel.relationship_id}: missing subject node {rel.subject_entity_id}")
            if rel.object_entity_id not in self.entities:
                raise ValueError(f"{rel.relationship_id}: missing object node {rel.object_entity_id}")
            self.relationships[rel.relationship_id] = rel
            self._out.setdefault(rel.subject_entity_id, []).append(rel)
            self._in.setdefault(rel.object_entity_id, []).append(rel)

    @classmethod
    def from_json_directory(cls, json_dir: str | Path) -> "SemanticGraph":
        json_dir = Path(json_dir)
        with open(json_dir / "entities.json", encoding="utf-8") as f:
            entities = json.load(f)
        with open(json_dir / "semantic_relationships.json", encoding="utf-8") as f:
            relationships = json.load(f)

        entities_by_id = {row["entity_id"]: row for row in entities}

        def add_operational_nodes(filename: str, id_field: str, type_name: str, name_field: str) -> None:
            path = json_dir / filename
            if not path.exists():
                return
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)
            for row in rows:
                entity_id = str(row.get(id_field, "")).strip()
                if not entity_id or entity_id in entities_by_id:
                    continue
                enriched = dict(row)
                enriched["entity_id"] = entity_id
                enriched["entity_type"] = type_name
                enriched["name"] = str(row.get(name_field, entity_id))
                entities_by_id[entity_id] = enriched

        add_operational_nodes("health_observations.json", "observation_id", "HEALTH_OBSERVATION", "observation_summary")
        add_operational_nodes("known_errors.json", "known_error_id", "KNOWN_ERROR", "title")
        add_operational_nodes("changes.json", "change_id", "CHANGE", "short_description")
        add_operational_nodes("knowledge_documents.json", "document_id", "KNOWLEDGE_DOCUMENT", "title")
        return cls(entities_by_id.values(), relationships)

    def get_entity(self, entity_id: str) -> Entity:
        try:
            return self.entities[entity_id]
        except KeyError as exc:
            raise KeyError(f"Unknown entity: {entity_id}") from exc

    def iter_neighbors(self, entity_id: str, *, direction: Direction = "both",
                       predicates: set[str] | None = None,
                       minimum_confidence: float = 0.0,
                       allowed_authorities: set[str] | None = None) -> Iterator[PathStep]:
        self.get_entity(entity_id)
        if direction in ("out", "both"):
            for rel in self._out.get(entity_id, []):
                if self._accept(rel, predicates, minimum_confidence, allowed_authorities):
                    yield PathStep(entity_id, rel, rel.object_entity_id, "out")
        if direction in ("in", "both"):
            for rel in self._in.get(entity_id, []):
                if self._accept(rel, predicates, minimum_confidence, allowed_authorities):
                    yield PathStep(entity_id, rel, rel.subject_entity_id, "in")

    @staticmethod
    def _accept(rel: Relationship, predicates: set[str] | None,
                minimum_confidence: float,
                allowed_authorities: set[str] | None) -> bool:
        if predicates is not None and rel.predicate not in predicates:
            return False
        if rel.confidence < minimum_confidence:
            return False
        if allowed_authorities is not None and rel.authority not in allowed_authorities:
            return False
        return True

    def follow(self, start_entity_id: str, *, predicate: str,
               direction: Literal["out", "in"],
               minimum_confidence: float = 0.0,
               allowed_authorities: set[str] | None = None) -> list[PathStep]:
        return list(self.iter_neighbors(
            start_entity_id,
            direction=direction,
            predicates={predicate},
            minimum_confidence=minimum_confidence,
            allowed_authorities=allowed_authorities,
        ))

    def format_step(self, step: PathStep) -> str:
        source = self.get_entity(step.from_entity_id)
        target = self.get_entity(step.to_entity_id)
        arrow = f"--{step.relationship.predicate}-->"
        if step.traversal_direction == "in":
            arrow = f"<--{step.relationship.predicate}--"
        return (
            f"{source.entity_id} ({source.name}) {arrow} "
            f"{target.entity_id} ({target.name}) "
            f"[{step.relationship.authority}, confidence={step.relationship.confidence:.2f}]"
        )

    def format_path(self, path: list[PathStep]) -> str:
        return "\n".join(self.format_step(step) for step in path)
