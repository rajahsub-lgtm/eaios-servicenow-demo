"""Does everything the dataset points at actually exist?

The cheapest class of incoherence and the one that fails most visibly: an
outcome referencing a pattern that was never generated counts as zero cases,
so a pattern the demonstration is built around silently has no experience
behind it. Nothing raises. The number is just wrong.
"""

from __future__ import annotations

from collections import Counter

from .dataset import Dataset
from .findings import Finding, error, info, warn


NAME = "referential"

# Every reference the fixtures make, as (file, field, target population).
# Adding a fixture means adding its references here; a reference nobody
# declared is a reference nobody checks.
REFERENCES = (
    # Relationship endpoints resolve against the graph's node population,
    # which includes promoted operational records — not entities.json alone.
    ("semantic_relationships", "subject_entity_id", "graph_nodes"),
    ("semantic_relationships", "object_entity_id", "graph_nodes"),
    ("known_errors", "applies_to_entity_id", "entities"),
    ("incidents", "entity_id", "entities"),
    ("changes", "entity_id", "entities"),
    ("problems", "entity_id", "entities"),
    ("health_observations", "entity_id", "entities"),
    ("telemetry_samples", "entity_id", "entities"),
    ("outcome_history", "entity_id", "entities"),
    ("learned_patterns", "applies_to_entity_id", "entities"),
)

IDENTITY = (
    ("entities", "entity_id"),
    ("semantic_relationships", "relationship_id"),
    ("known_errors", "known_error_id"),
    ("outcome_history", "outcome_id"),
    ("incidents", "incident_id"),
    ("changes", "change_id"),
    ("problems", "problem_id"),
    ("knowledge_documents", "document_id"),
    ("health_observations", "observation_id"),
    ("telemetry_samples", "sample_id"),
    ("metric_definitions", "metric_id"),
    ("scenarios", "scenario_id"),
)


def validate(dataset: Dataset) -> list[Finding]:
    findings: list[Finding] = []

    for problem in dataset.load_errors:
        findings.append(
            error(
                NAME,
                "loadable",
                f"file could not be parsed: {problem}",
                consequence="Every downstream validator sees this fixture as empty.",
            )
        )

    findings += _unique_identifiers(dataset)
    findings += _dangling_references(dataset)
    findings += _pattern_references(dataset)
    findings += _document_entities(dataset)
    findings += _orphan_entities(dataset)
    return findings


def _unique_identifiers(dataset: Dataset) -> list[Finding]:
    findings = []
    for fixture, key in IDENTITY:
        rows = dataset[fixture]
        if not rows:
            continue
        counts = Counter(str(row.get(key)) for row in rows if row.get(key))
        duplicates = {k: v for k, v in counts.items() if v > 1}
        missing = sum(1 for row in rows if not row.get(key))
        if duplicates:
            findings.append(
                error(
                    NAME,
                    "unique_identity",
                    f"{len(duplicates)} duplicated {key} in {fixture}",
                    subject=fixture,
                    consequence=(
                        "Lookups keyed on this field return one record and "
                        "silently discard the rest."
                    ),
                    detail={"examples": dict(list(duplicates.items())[:5])},
                )
            )
        if missing:
            findings.append(
                error(
                    NAME,
                    "identity_present",
                    f"{missing} rows in {fixture} have no {key}",
                    subject=fixture,
                )
            )
    return findings


def _dangling_references(dataset: Dataset) -> list[Finding]:
    findings = []
    for fixture, field_name, target in REFERENCES:
        rows = dataset[fixture]
        if not rows:
            continue
        population = {
            "entities": dataset.entity_ids,
            "graph_nodes": dataset.graph_node_ids,
        }.get(target, set())
        if not population:
            continue
        dangling = Counter(
            str(row[field_name])
            for row in rows
            if row.get(field_name) and str(row[field_name]) not in population
        )
        if dangling:
            findings.append(
                error(
                    NAME,
                    "reference_exists",
                    f"{sum(dangling.values())} rows in {fixture} reference "
                    f"{len(dangling)} {target.rstrip('s')} id(s) that do not exist",
                    subject=f"{fixture}.{field_name}",
                    consequence=(
                        "Graph traversal drops these silently; the record "
                        "exists but is unreachable from the topology."
                    ),
                    detail={"examples": list(dangling)[:5]},
                )
            )
    return findings


def _pattern_references(dataset: Dataset) -> list[Finding]:
    """Outcomes and incidents pointing at patterns.

    Kept separate because the population is the union of curated and learned
    patterns, and because this is the reference whose failure is invisible:
    an outcome against a non-existent pattern does not error, it just never
    counts toward anything.
    """
    findings = []
    patterns = dataset.pattern_ids
    if not patterns:
        return findings

    for fixture in ("outcome_history", "incidents", "problems"):
        rows = dataset[fixture]
        if not rows:
            continue
        dangling = Counter(
            str(row["known_error_id"])
            for row in rows
            if row.get("known_error_id")
            and str(row["known_error_id"]) not in patterns
        )
        if dangling:
            severity = error if fixture == "outcome_history" else warn
            findings.append(
                severity(
                    NAME,
                    "pattern_exists",
                    f"{sum(dangling.values())} rows in {fixture} reference "
                    f"{len(dangling)} pattern(s) that do not exist",
                    subject=f"{fixture}.known_error_id",
                    consequence=(
                        "The experience ledger counts zero cases for these, "
                        "so a pattern the demonstration relies on has no "
                        "history behind it and nothing reports the loss."
                    ),
                    detail={"examples": list(dangling)[:5]},
                )
            )
    return findings


def _document_entities(dataset: Dataset) -> list[Finding]:
    """Knowledge documents name the entities they cover as a delimited string."""
    findings = []
    entities = dataset.entity_ids
    if not entities:
        return findings

    dangling = Counter()
    for row in dataset["knowledge_documents"]:
        raw = row.get("entity_ids", "")
        listed = (
            raw
            if isinstance(raw, (list, tuple))
            else [p.strip() for p in str(raw).split(",")]
        )
        for entity in listed:
            if entity and entity not in entities:
                dangling[entity] += 1

    if dangling:
        findings.append(
            error(
                NAME,
                "document_entity_exists",
                f"{len(dangling)} entity id(s) named by documents do not exist",
                subject="knowledge_documents.entity_ids",
                consequence=(
                    "Documentation eligibility requires an entity match, so "
                    "these documents can never be admitted for any case."
                ),
                detail={"examples": list(dangling)[:5]},
            )
        )
    return findings


def _orphan_entities(dataset: Dataset) -> list[Finding]:
    """Entities no relationship touches.

    Not an error — a generated enterprise may legitimately hold leaf assets —
    but a high proportion means the topology generator produced a population
    rather than a graph, and traversal will find nothing interesting.
    """
    entities = dataset.entity_ids
    if not entities:
        return []

    connected = set()
    for row in dataset["semantic_relationships"]:
        connected.add(str(row.get("subject_entity_id")))
        connected.add(str(row.get("object_entity_id")))

    orphans = entities - connected
    if not orphans:
        return []

    share = len(orphans) / len(entities)
    reporter = warn if share > 0.10 else info
    return [
        reporter(
            NAME,
            "topology_coverage",
            f"{len(orphans)} of {len(entities)} entities "
            f"({share:.0%}) have no relationships",
            consequence=(
                "Entities outside the graph cannot be reached by traversal "
                "and cannot participate in shared-dependency reasoning."
            )
            if share > 0.10
            else "",
            detail={"examples": sorted(orphans)[:5]},
        )
    ]
