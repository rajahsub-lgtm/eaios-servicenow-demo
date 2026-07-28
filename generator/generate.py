from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .io_utils import ensure_dirs, write_csv, write_json, write_jsonl, sha256_file
from .spec import GeneratorSpec
from .stable_rng import rng_for, stable_choice, stable_float, stable_sample

UTC = timezone.utc
BASE_TIME = datetime(2024, 1, 1, tzinfo=UTC)

ENTITY_BLUEPRINT = [
    ("BUSINESS_OUTCOME", 20),
    ("BUSINESS_CAPABILITY", 100),
    ("BUSINESS_APPLICATION", 180),
    ("APPLICATION_SERVICE", 300),
    ("SOFTWARE_COMPONENT", 500),
    ("CLOUD_RESOURCE", 350),
    ("DATA_STORE", 160),
    ("SHARED_INFRASTRUCTURE", 140),
    ("EXTERNAL_VENDOR_SERVICE", 60),
    ("SUPPORT_TEAM", 120),
    ("POLICY_OR_CREDENTIAL", 70),
]

REGIONS = ["US-WEST", "US-EAST", "EU-WEST", "EU-CENTRAL", "AP-SOUTH", "AP-NORTHEAST", "LATAM", "GLOBAL"]
BUSINESS_UNITS = ["Commerce", "Finance", "HR", "Manufacturing", "Supply Chain", "Sales", "Support", "Engineering", "Security", "Data", "Legal", "Corporate"]
SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ONSET_SHAPES = ["STEP", "GRADUAL", "PERIODIC", "BURST", "POST_CHANGE_STEP"]
PRESENTATIONS = [
    ("authentication failure", "authentication_failure_rate", "UP"),
    ("connection failure", "connection_failure_rate", "UP"),
    ("latency increase", "request_latency_ms", "UP"),
    ("request timeout", "request_timeout_rate", "UP"),
    ("transaction failure", "transaction_failure_rate", "UP"),
    ("service degradation", "service_error_rate", "UP"),
    ("queue delay", "queue_depth", "UP"),
]
CAUSE_FAMILIES = [
    "CONFIGURATION_DRIFT",
    "CAPACITY_EXHAUSTION",
    "CERTIFICATE_EXPIRY",
    "IDENTITY_DEGRADATION",
    "NETWORK_PATH_DEGRADATION",
    "EXTERNAL_VENDOR_OUTAGE",
    "SOFTWARE_REGRESSION",
    "DATA_STORE_CONTENTION",
    "QUEUE_BACKLOG",
    "SECURE_GATEWAY_POLICY",
]
SYMPTOMS_BY_CAUSE = {
    "CONFIGURATION_DRIFT": ["authentication failure", "transaction failure", "service degradation"],
    "CAPACITY_EXHAUSTION": ["latency increase", "request timeout", "service degradation"],
    "CERTIFICATE_EXPIRY": ["authentication failure", "connection failure", "request timeout"],
    "IDENTITY_DEGRADATION": ["authentication failure", "transaction failure", "service degradation"],
    "NETWORK_PATH_DEGRADATION": ["connection failure", "latency increase", "request timeout"],
    "EXTERNAL_VENDOR_OUTAGE": ["service degradation", "request timeout", "connection failure"],
    "SOFTWARE_REGRESSION": ["transaction failure", "service degradation", "latency increase"],
    "DATA_STORE_CONTENTION": ["latency increase", "transaction failure", "request timeout"],
    "QUEUE_BACKLOG": ["queue delay", "latency increase", "service degradation"],
    "SECURE_GATEWAY_POLICY": ["authentication failure", "connection failure", "service degradation"],
}
METRICS_BY_CAUSE = {
    "CONFIGURATION_DRIFT": [("authentication_failure_rate", "UP"), ("transaction_failure_rate", "UP")],
    "CAPACITY_EXHAUSTION": [("request_latency_ms", "UP"), ("request_timeout_rate", "UP")],
    "CERTIFICATE_EXPIRY": [("authentication_failure_rate", "UP"), ("connection_failure_rate", "UP")],
    "IDENTITY_DEGRADATION": [("authentication_failure_rate", "UP"), ("transaction_failure_rate", "UP")],
    "NETWORK_PATH_DEGRADATION": [("connection_failure_rate", "UP"), ("request_latency_ms", "UP")],
    "EXTERNAL_VENDOR_OUTAGE": [("request_timeout_rate", "UP"), ("connection_failure_rate", "UP")],
    "SOFTWARE_REGRESSION": [("transaction_failure_rate", "UP"), ("request_latency_ms", "UP")],
    "DATA_STORE_CONTENTION": [("request_latency_ms", "UP"), ("transaction_failure_rate", "UP")],
    "QUEUE_BACKLOG": [("queue_depth", "UP"), ("request_latency_ms", "UP")],
    "SECURE_GATEWAY_POLICY": [("authentication_failure_rate", "UP"), ("connection_failure_rate", "UP")],
}
REMEDIATIONS = {
    "CONFIGURATION_DRIFT": [("RESTORE_GOVERNED_CONFIGURATION", 0.88, 0.08), ("RESTART_COMPONENT", 0.30, 0.55)],
    "CAPACITY_EXHAUSTION": [("SCALE_CAPACITY", 0.91, 0.07), ("RESTART_COMPONENT", 0.42, 0.45)],
    "CERTIFICATE_EXPIRY": [("ROTATE_CERTIFICATE", 0.97, 0.02), ("RESTART_COMPONENT", 0.08, 0.82)],
    "IDENTITY_DEGRADATION": [("RESTORE_IDENTITY_DEPENDENCY", 0.90, 0.05), ("CLEAR_CLIENT_CACHE", 0.22, 0.65)],
    "NETWORK_PATH_DEGRADATION": [("REROUTE_TRAFFIC", 0.86, 0.12), ("RESTART_APPLICATION", 0.12, 0.78)],
    "EXTERNAL_VENDOR_OUTAGE": [("WAIT_AND_FAILOVER", 0.82, 0.14), ("RESTART_INTERNAL_SERVICE", 0.10, 0.80)],
    "SOFTWARE_REGRESSION": [("ROLLBACK_RELEASE", 0.94, 0.04), ("RESTART_COMPONENT", 0.36, 0.48)],
    "DATA_STORE_CONTENTION": [("TERMINATE_BLOCKING_WORKLOAD", 0.84, 0.15), ("RESTART_DATABASE", 0.61, 0.25)],
    "QUEUE_BACKLOG": [("SCALE_CONSUMERS", 0.89, 0.10), ("PURGE_QUEUE", 0.54, 0.30)],
    "SECURE_GATEWAY_POLICY": [("ROLLBACK_GATEWAY_POLICY", 0.95, 0.03), ("RESTART_GATEWAY", 0.28, 0.67)],
}
ENTITY_COMPATIBILITY = {
    "CONFIGURATION_DRIFT": ["SOFTWARE_COMPONENT", "POLICY_OR_CREDENTIAL", "SHARED_INFRASTRUCTURE"],
    "CAPACITY_EXHAUSTION": ["SOFTWARE_COMPONENT", "CLOUD_RESOURCE", "DATA_STORE"],
    "CERTIFICATE_EXPIRY": ["POLICY_OR_CREDENTIAL", "SHARED_INFRASTRUCTURE", "SOFTWARE_COMPONENT"],
    "IDENTITY_DEGRADATION": ["SHARED_INFRASTRUCTURE", "EXTERNAL_VENDOR_SERVICE"],
    "NETWORK_PATH_DEGRADATION": ["SHARED_INFRASTRUCTURE", "CLOUD_RESOURCE"],
    "EXTERNAL_VENDOR_OUTAGE": ["EXTERNAL_VENDOR_SERVICE"],
    "SOFTWARE_REGRESSION": ["SOFTWARE_COMPONENT", "APPLICATION_SERVICE"],
    "DATA_STORE_CONTENTION": ["DATA_STORE"],
    "QUEUE_BACKLOG": ["DATA_STORE", "SOFTWARE_COMPONENT"],
    "SECURE_GATEWAY_POLICY": ["SHARED_INFRASTRUCTURE", "POLICY_OR_CREDENTIAL"],
}


def _scaled_entity_counts(total: int) -> dict[str, int]:
    base_total = sum(v for _, v in ENTITY_BLUEPRINT)
    raw = {k: total * v / base_total for k, v in ENTITY_BLUEPRINT}
    counts = {k: int(math.floor(v)) for k, v in raw.items()}
    remainder = total - sum(counts.values())
    for k, _ in sorted(raw.items(), key=lambda item: item[1] - math.floor(item[1]), reverse=True)[:remainder]:
        counts[k] += 1
    return counts


def _entity_prefix(entity_type: str) -> str:
    return {
        "BUSINESS_OUTCOME": "BO",
        "BUSINESS_CAPABILITY": "CAP",
        "BUSINESS_APPLICATION": "APP",
        "APPLICATION_SERVICE": "SVC",
        "SOFTWARE_COMPONENT": "COMP",
        "CLOUD_RESOURCE": "CLOUD",
        "DATA_STORE": "DATA",
        "SHARED_INFRASTRUCTURE": "INFRA",
        "EXTERNAL_VENDOR_SERVICE": "VENDOR",
        "SUPPORT_TEAM": "TEAM",
        "POLICY_OR_CREDENTIAL": "POL",
    }[entity_type]


def generate_entities(spec: GeneratorSpec) -> list[dict[str, Any]]:
    counts = _scaled_entity_counts(spec.scale.entities)
    rows: list[dict[str, Any]] = []
    for entity_type, count in counts.items():
        for i in range(1, count + 1):
            entity_id = f"{_entity_prefix(entity_type)}-{i:04d}"
            region = "GLOBAL" if entity_type in {"BUSINESS_OUTCOME", "EXTERNAL_VENDOR_SERVICE"} else stable_choice(REGIONS, spec.seed, "entity-region", entity_type, i)
            business_unit = stable_choice(BUSINESS_UNITS, spec.seed, "entity-bu", entity_type, i)
            criticality = stable_choice(["LOW", "MEDIUM", "HIGH", "CRITICAL"], spec.seed, "criticality", entity_type, i)
            provider = "EXTERNAL_VENDOR" if entity_type == "EXTERNAL_VENDOR_SERVICE" else "INTERNAL"
            rows.append({
                "entity_id": entity_id,
                "entity_type": entity_type,
                "name": f"{entity_type.replace('_', ' ').title()} {i:04d}",
                "region": region,
                "business_unit": business_unit,
                "criticality": criticality,
                "service_provider_type": provider,
                "trust_level": "TRUSTED" if stable_float(spec.seed, "trust", entity_id) > 0.08 else "CONDITIONAL",
                "lifecycle_status": "ACTIVE",
                "data_classification": spec.data_classification,
            })
    assert len(rows) == spec.scale.entities
    return rows


def _add_edge(edges: list[dict[str, Any]], seen: set[tuple[str, str, str]], source: str, predicate: str, target: str, spec: GeneratorSpec, authority: str = "AUTHORITATIVE") -> bool:
    key = (source, predicate, target)
    if source == target or key in seen:
        return False
    seen.add(key)
    edge_id = f"REL-{len(edges)+1:06d}"
    confidence = 1.0 if authority == "AUTHORITATIVE" else round(0.65 + 0.3 * stable_float(spec.seed, "edge-confidence", edge_id), 3)
    edges.append({
        "relationship_id": edge_id,
        "source_entity_id": source,
        "relationship_type": predicate,
        "target_entity_id": target,
        "relationship_authority": authority,
        "confidence": confidence,
        "lifecycle_status": "ACTIVE",
        "data_classification": spec.data_classification,
    })
    return True


def generate_relationships(spec: GeneratorSpec, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_type: dict[str, list[str]] = defaultdict(list)
    for row in entities:
        by_type[row["entity_type"]].append(row["entity_id"])
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    # Mandatory semantic spine.
    for i, cap in enumerate(by_type["BUSINESS_CAPABILITY"]):
        _add_edge(edges, seen, cap, "CONTRIBUTES_TO", by_type["BUSINESS_OUTCOME"][i % len(by_type["BUSINESS_OUTCOME"])], spec)
    for i, app in enumerate(by_type["BUSINESS_APPLICATION"]):
        for j in range(2):
            _add_edge(edges, seen, app, "SUPPORTS", by_type["BUSINESS_CAPABILITY"][(i * 2 + j) % len(by_type["BUSINESS_CAPABILITY"])], spec)
    for i, service in enumerate(by_type["APPLICATION_SERVICE"]):
        _add_edge(edges, seen, service, "IMPLEMENTS", by_type["BUSINESS_APPLICATION"][i % len(by_type["BUSINESS_APPLICATION"])], spec)
        _add_edge(edges, seen, service, "SUPPORTS", by_type["BUSINESS_CAPABILITY"][(i * 3) % len(by_type["BUSINESS_CAPABILITY"])], spec)
    for i, comp in enumerate(by_type["SOFTWARE_COMPONENT"]):
        _add_edge(edges, seen, comp, "PART_OF", by_type["APPLICATION_SERVICE"][i % len(by_type["APPLICATION_SERVICE"])], spec)
        if i % 2 == 0:
            _add_edge(edges, seen, comp, "DEPENDS_ON", by_type["DATA_STORE"][i % len(by_type["DATA_STORE"])], spec)
        _add_edge(edges, seen, comp, "HOSTED_ON", by_type["CLOUD_RESOURCE"][i % len(by_type["CLOUD_RESOURCE"])], spec)
        if i % 3 == 0:
            _add_edge(edges, seen, comp, "ROUTED_THROUGH", by_type["SHARED_INFRASTRUCTURE"][i % len(by_type["SHARED_INFRASTRUCTURE"])], spec)
    for i, service in enumerate(by_type["APPLICATION_SERVICE"]):
        if i % 4 == 0:
            _add_edge(edges, seen, service, "DEPENDS_ON", by_type["EXTERNAL_VENDOR_SERVICE"][i % len(by_type["EXTERNAL_VENDOR_SERVICE"])], spec)
        if i % 5 == 0:
            _add_edge(edges, seen, service, "ROUTED_THROUGH", by_type["SHARED_INFRASTRUCTURE"][i % len(by_type["SHARED_INFRASTRUCTURE"])], spec)
        _add_edge(edges, seen, service, "OWNED_BY", by_type["SUPPORT_TEAM"][i % len(by_type["SUPPORT_TEAM"])], spec)
    for i, infra in enumerate(by_type["SHARED_INFRASTRUCTURE"]):
        if by_type["POLICY_OR_CREDENTIAL"]:
            _add_edge(edges, seen, by_type["POLICY_OR_CREDENTIAL"][i % len(by_type["POLICY_OR_CREDENTIAL"])], "MODIFIES", infra, spec)
        _add_edge(edges, seen, infra, "OWNED_BY", by_type["SUPPORT_TEAM"][(i * 2) % len(by_type["SUPPORT_TEAM"])], spec)

    compatibility = [
        ("SOFTWARE_COMPONENT", "DEPENDS_ON", "SOFTWARE_COMPONENT"),
        ("SOFTWARE_COMPONENT", "DEPENDS_ON", "DATA_STORE"),
        ("APPLICATION_SERVICE", "DEPENDS_ON", "APPLICATION_SERVICE"),
        ("APPLICATION_SERVICE", "ROUTED_THROUGH", "SHARED_INFRASTRUCTURE"),
        ("APPLICATION_SERVICE", "AUTHENTICATES_WITH", "SHARED_INFRASTRUCTURE"),
        ("APPLICATION_SERVICE", "DEPENDS_ON", "EXTERNAL_VENDOR_SERVICE"),
        ("CLOUD_RESOURCE", "CONNECTED_TO", "SHARED_INFRASTRUCTURE"),
        ("DATA_STORE", "REPLICATES_TO", "DATA_STORE"),
        ("POLICY_OR_CREDENTIAL", "APPLIES_TO", "SOFTWARE_COMPONENT"),
        ("POLICY_OR_CREDENTIAL", "APPLIES_TO", "APPLICATION_SERVICE"),
        ("SUPPORT_TEAM", "SUPPORTS", "APPLICATION_SERVICE"),
    ]
    attempt = 0
    while len(edges) < spec.scale.relationships:
        source_type, predicate, target_type = compatibility[attempt % len(compatibility)]
        source = stable_choice(by_type[source_type], spec.seed, "edge-source", attempt)
        target = stable_choice(by_type[target_type], spec.seed, "edge-target", attempt)
        authority = "AUTHORITATIVE" if stable_float(spec.seed, "edge-auth", attempt) > 0.18 else "DISCOVERED"
        _add_edge(edges, seen, source, predicate, target, spec, authority)
        attempt += 1
        if attempt > spec.scale.relationships * 100:
            raise RuntimeError("Unable to generate requested unique relationship count")
    assert len(edges) == spec.scale.relationships
    return edges


def generate_patterns(spec: GeneratorSpec, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_type: dict[str, list[str]] = defaultdict(list)
    for row in entities:
        by_type[row["entity_type"]].append(row["entity_id"])
    patterns: list[dict[str, Any]] = []
    for i in range(spec.scale.patterns):
        family = CAUSE_FAMILIES[i % len(CAUSE_FAMILIES)]
        compatible_type = ENTITY_COMPATIBILITY[family][i % len(ENTITY_COMPATIBILITY[family])]
        applies_to = stable_choice(by_type[compatible_type], spec.seed, "pattern-entity", i)
        symptom = SYMPTOMS_BY_CAUSE[family][i % len(SYMPTOMS_BY_CAUSE[family])]
        metric, direction = METRICS_BY_CAUSE[family][i % len(METRICS_BY_CAUSE[family])]
        remediation, efficacy, recurrence = REMEDIATIONS[family][0]
        patterns.append({
            "known_error_id": f"KE-{i+1:04d}",
            "cause_family": family,
            "applies_to_entity_id": applies_to,
            "compatible_entity_type": compatible_type,
            "symptom_category": symptom,
            "trigger_metric_id": metric,
            "breach_direction": direction,
            "onset_shape": ONSET_SHAPES[i % len(ONSET_SHAPES)],
            "recommended_action": remediation,
            "base_remediation_efficacy": efficacy,
            "base_recurrence_probability": recurrence,
            "knowledge_status": "PUBLISHED",
            "trust_level": "TRUSTED" if i % 9 else "CONDITIONAL",
            "valid_from": (BASE_TIME - timedelta(days=365)).isoformat(),
            "valid_to": "",
            "data_classification": spec.data_classification,
        })
    return patterns


def allocate_long_tail(spec: GeneratorSpec) -> list[int]:
    n = spec.scale.patterns
    target = spec.scale.outcomes
    if n <= 20:
        doc_only = max(2, n // 10)
        sparse = max(3, n // 5)
        emerging = max(3, n // 5)
        developing = max(3, n // 5)
        established = max(2, n // 10)
    else:
        doc_only, sparse, emerging, developing, established = 10, 20, 20, 20, 15
    dominant = n - doc_only - sparse - emerging - developing - established
    counts = [0] * doc_only
    for i in range(sparse):
        counts.append(1 + (i % 4))
    for i in range(emerging):
        counts.append(5 + (i * 3 % 10))
    for i in range(developing):
        counts.append(15 + (i * 13 % 85))
    for i in range(established):
        counts.append(120 + (i * 71 % 780))
    remaining = target - sum(counts)
    weights = [1 / ((i + 1) ** 1.15) for i in range(max(1, dominant))]
    weight_sum = sum(weights)
    dom_counts = [max(1, int(remaining * w / weight_sum)) for w in weights]
    diff = remaining - sum(dom_counts)
    idx = 0
    while diff != 0:
        j = idx % len(dom_counts)
        if diff > 0:
            dom_counts[j] += 1
            diff -= 1
        elif dom_counts[j] > 1:
            dom_counts[j] -= 1
            diff += 1
        idx += 1
    counts.extend(dom_counts)
    assert len(counts) == n and sum(counts) == target
    return counts


def _build_graph_maps(relationships: list[dict[str, Any]]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    forward: dict[str, list[str]] = defaultdict(list)
    reverse: dict[str, list[str]] = defaultdict(list)
    for edge in relationships:
        forward[edge["source_entity_id"]].append(edge["target_entity_id"])
        reverse[edge["target_entity_id"]].append(edge["source_entity_id"])
    return forward, reverse


def _bounded_reachable(start: str, graph: dict[str, list[str]], max_depth: int = 4, limit: int = 30) -> list[str]:
    result: list[str] = []
    seen = {start}
    q: deque[tuple[str, int]] = deque([(start, 0)])
    while q and len(result) < limit:
        node, depth = q.popleft()
        if depth >= max_depth:
            continue
        for nxt in graph.get(node, []):
            if nxt in seen:
                continue
            seen.add(nxt)
            result.append(nxt)
            q.append((nxt, depth + 1))
            if len(result) >= limit:
                break
    return result


def _find_trigger_service(root: str, entity_by_id: dict[str, dict[str, Any]], forward: dict[str, list[str]], reverse: dict[str, list[str]]) -> str:
    if entity_by_id[root]["entity_type"] == "APPLICATION_SERVICE":
        return root
    seen = {root}
    q: deque[tuple[str, int]] = deque([(root, 0)])
    while q:
        node, depth = q.popleft()
        if depth >= 4:
            continue
        neighbors = sorted(set(forward.get(node, [])) | set(reverse.get(node, [])))
        for nxt in neighbors:
            if nxt in seen:
                continue
            seen.add(nxt)
            if entity_by_id.get(nxt, {}).get("entity_type") == "APPLICATION_SERVICE":
                return nxt
            q.append((nxt, depth + 1))
    services = sorted(k for k, v in entity_by_id.items() if v["entity_type"] == "APPLICATION_SERVICE")
    return services[abs(hash(root)) % len(services)]


def _support_team_for(entity_id: str, relationships: list[dict[str, Any]], teams: list[str]) -> str:
    for edge in relationships:
        if edge["source_entity_id"] == entity_id and edge["relationship_type"] == "OWNED_BY":
            return edge["target_entity_id"]
    return teams[hash(entity_id) % len(teams)]


def _severity(spec: GeneratorSpec, episode_index: int) -> str:
    x = stable_float(spec.seed, "severity", episode_index)
    if x < 0.06:
        return "CRITICAL"
    if x < 0.31:
        return "HIGH"
    if x < 0.76:
        return "MEDIUM"
    return "LOW"


def _outcome_for(spec: GeneratorSpec, episode_id: str, correct_action: bool, efficacy: float, recurrence_base: float, rejected: bool, human_corrected: bool) -> tuple[str, bool, int, float]:
    if rejected:
        return "NOT_EXECUTED", False, 0, 0.0
    effective = efficacy if correct_action else min(0.25, efficacy * 0.25)
    if human_corrected:
        effective = min(0.98, effective + 0.18)
    succeeded = stable_float(spec.seed, "outcome-success", episode_id) < effective
    recurrence = succeeded and stable_float(spec.seed, "outcome-recurrence", episode_id) < recurrence_base
    recovery = int(8 + 180 * stable_float(spec.seed, "recovery", episode_id)) if succeeded else int(90 + 500 * stable_float(spec.seed, "recovery-fail", episode_id))
    usefulness = round(0.35 + 0.6 * stable_float(spec.seed, "usefulness", episode_id), 3)
    return ("RESOLVED" if succeeded else "NOT_RESOLVED"), recurrence, recovery, usefulness


def generate_operational_history(
    spec: GeneratorSpec,
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    patterns: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    entity_by_id = {r["entity_id"]: r for r in entities}
    by_type: dict[str, list[str]] = defaultdict(list)
    for r in entities:
        by_type[r["entity_type"]].append(r["entity_id"])
    forward, reverse = _build_graph_maps(relationships)
    owner_map = {
        edge["source_entity_id"]: edge["target_entity_id"]
        for edge in relationships
        if edge["relationship_type"] == "OWNED_BY"
    }
    counts = allocate_long_tail(spec)
    incidents: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    truth: list[dict[str, Any]] = []
    detailed_ids: set[str] = set()
    episode_index = 0

    # Reserve ambiguity episodes and force them into patterns with compatible families.
    ambiguity_episode_slots = spec.scale.ambiguity_pairs * 2
    detailed_target = max(spec.scale.detailed_episodes, ambiguity_episode_slots)

    for pattern_index, (pattern, count) in enumerate(zip(patterns, counts)):
        compatible = by_type[pattern["compatible_entity_type"]]
        for local_idx in range(count):
            episode_index += 1
            episode_id = f"EP-{episode_index:06d}"
            incident_id = f"INC-{episode_index:06d}"
            outcome_id = f"OUT-{episode_index:06d}"
            root_entity = compatible[(pattern_index * 17 + local_idx * 7) % len(compatible)]
            trigger_entity = _find_trigger_service(root_entity, entity_by_id, forward, reverse)
            entity = entity_by_id[trigger_entity]
            start = BASE_TIME + timedelta(minutes=episode_index * 17)
            severity = _severity(spec, episode_index)
            symptom, metric, direction = PRESENTATIONS[int(stable_float(spec.seed, "presentation", episode_id) * len(PRESENTATIONS)) % len(PRESENTATIONS)]
            onset = ONSET_SHAPES[int(stable_float(spec.seed, "onset", episode_id) * len(ONSET_SHAPES)) % len(ONSET_SHAPES)]
            impacted = sorted(set(_bounded_reachable(root_entity, forward, max_depth=3, limit=12) + _bounded_reachable(root_entity, reverse, max_depth=3, limit=12)))
            blast_radius = max(1, len(impacted))
            support_team = owner_map.get(trigger_entity, by_type["SUPPORT_TEAM"][episode_index % len(by_type["SUPPORT_TEAM"])])
            base_change_rate = 0.24 + (0.10 if pattern["cause_family"] in {"CONFIGURATION_DRIFT", "SOFTWARE_REGRESSION", "SECURE_GATEWAY_POLICY"} else 0.0)
            recent_change = stable_float(spec.seed, "recent-change", episode_id) < base_change_rate
            change_id = ""
            if recent_change:
                change_id = f"CHG-{episode_index:06d}"
                changes.append({
                    "change_id": change_id,
                    "entity_id": root_entity,
                    "implemented_at": (start - timedelta(minutes=30 + int(180 * stable_float(spec.seed, "change-offset", episode_id)))).isoformat(),
                    "risk": "HIGH" if severity in {"HIGH", "CRITICAL"} else "MEDIUM",
                    "change_type": "POLICY" if pattern["cause_family"] in {"SECURE_GATEWAY_POLICY", "CONFIGURATION_DRIFT"} else "STANDARD",
                    "state": "IMPLEMENTED",
                    "data_classification": spec.data_classification,
                })
            vendor_status = "UNKNOWN" if stable_float(spec.seed, "vendor-status", episode_id) < 0.35 else "NOT_CHECKED"
            observation_id = f"OBS-{episode_index:06d}"
            observations.append({
                "observation_id": observation_id,
                "episode_id": episode_id,
                "entity_id": trigger_entity,
                "metric_id": metric,
                "breach_direction": direction,
                "observed_at": (start + timedelta(minutes=3)).isoformat(),
                "severity": severity,
                "value_band": "SEVERE" if severity in {"HIGH", "CRITICAL"} else "ELEVATED",
                "data_classification": spec.data_classification,
            })
            incident_opened = start + timedelta(minutes=12)
            incidents.append({
                "incident_id": incident_id,
                "episode_id": episode_id,
                "observation_id": observation_id,
                "entity_id": trigger_entity,
                "entity_type": entity["entity_type"],
                "opened_at": incident_opened.isoformat(),
                "region": entity["region"],
                "business_unit": entity["business_unit"],
                "severity": severity,
                "symptom_category": symptom,
                "onset_shape": onset,
                "blast_radius_band": "CROSS_PLATFORM" if blast_radius >= 8 else ("MULTI_SERVICE" if blast_radius >= 4 else "LOCAL"),
                "support_team_id": support_team,
                "recent_change_present": recent_change,
                "vendor_status_at_onset": vendor_status,
                "short_description": f"{symptom.title()} affecting {entity['name']}",
                "state": "CLOSED",
                "data_classification": spec.data_classification,
            })
            # Human behavior and action selection are generated independently of production confidence.
            rejected = stable_float(spec.seed, "approval-reject", episode_id) < (0.06 + (0.06 if severity == "CRITICAL" else 0))
            human_corrected = (not rejected) and stable_float(spec.seed, "human-correct", episode_id) < 0.18
            chose_correct = human_corrected or stable_float(spec.seed, "action-choice", episode_id) < 0.83
            correct_action = pattern["recommended_action"]
            wrong_action = REMEDIATIONS[pattern["cause_family"]][1][0]
            proposed_action = correct_action if chose_correct else wrong_action
            final_action = correct_action if human_corrected else proposed_action
            actual_outcome, recurrence, recovery, usefulness = _outcome_for(
                spec,
                episode_id,
                final_action == correct_action,
                float(pattern["base_remediation_efficacy"]),
                float(pattern["base_recurrence_probability"]),
                rejected,
                human_corrected,
            )
            approval = "REJECTED" if rejected else "APPROVED"
            human_mod = "" if not human_corrected else "CHANGED_REMEDIATION"
            outcomes.append({
                "outcome_id": outcome_id,
                "incident_id": incident_id,
                "episode_id": episode_id,
                "known_error_id": pattern["known_error_id"],
                "scenario_pattern": pattern["cause_family"],
                "entity_id": root_entity,
                "recommendation": proposed_action,
                "approval_decision": approval,
                "human_modification": human_mod,
                "action_performed": "" if rejected else final_action,
                "outcome": actual_outcome,
                "recovery_minutes": recovery,
                "recurrence_within_24h": recurrence,
                "prior_confidence": "",  # Deliberately omitted to prevent circular history.
                "evidence_usefulness_score": usefulness,
                "recorded_at": (incident_opened + timedelta(minutes=max(20, recovery))).isoformat(),
                "data_classification": spec.data_classification,
            })
            truth.append({
                "episode_id": episode_id,
                "incident_id": incident_id,
                "true_cause_family": pattern["cause_family"],
                "true_root_entity_id": root_entity,
                "true_pattern_id": pattern["known_error_id"],
                "correct_remediation": correct_action,
                "propagation_targets": sorted(set([trigger_entity, *impacted])),
                "change_id": change_id,
                "cause_selection_stream": f"cause:{pattern_index}:{local_idx}",
                "background_stream": f"background:{episode_id}",
                "data_classification": spec.data_classification,
            })
            if episode_index <= detailed_target:
                detailed_ids.add(episode_id)

    assert len(outcomes) == spec.scale.outcomes == len(incidents)
    return {
        "incidents": incidents,
        "observations": observations,
        "changes": changes,
        "outcomes": outcomes,
        "truth": truth,
        "detailed_ids": [{"episode_id": x} for x in sorted(detailed_ids)],
    }


def generate_ambiguity_and_telemetry(
    spec: GeneratorSpec,
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    patterns: list[dict[str, Any]],
    history: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    incidents = history["incidents"]
    observations = history["observations"]
    outcomes = history["outcomes"]
    truth = history["truth"]
    incident_by_episode = {r["episode_id"]: r for r in incidents}
    entity_by_id = {r["entity_id"]: r for r in entities}
    patterns_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pattern in patterns:
        patterns_by_family[pattern["cause_family"]].append(pattern)
    service_paths: list[tuple[str, str, str]] = []
    routed: dict[str, list[str]] = defaultdict(list)
    vendors: dict[str, list[str]] = defaultdict(list)
    owners: dict[str, str] = {}
    for edge in relationships:
        if edge["relationship_type"] == "ROUTED_THROUGH":
            routed[edge["source_entity_id"]].append(edge["target_entity_id"])
        elif edge["relationship_type"] == "DEPENDS_ON" and entity_by_id.get(edge["target_entity_id"], {}).get("entity_type") == "EXTERNAL_VENDOR_SERVICE":
            vendors[edge["source_entity_id"]].append(edge["target_entity_id"])
        elif edge["relationship_type"] == "OWNED_BY":
            owners[edge["source_entity_id"]] = edge["target_entity_id"]
    for service in sorted(set(routed) & set(vendors)):
        for infra in routed[service]:
            for vendor in vendors[service]:
                service_paths.append((service, infra, vendor))
    observation_by_episode = {r["episode_id"]: r for r in observations}
    outcome_by_episode = {r["episode_id"]: r for r in outcomes}
    truth_by_episode = {r["episode_id"]: r for r in truth}

    telemetry: list[dict[str, Any]] = []
    runtime_events: list[dict[str, Any]] = []
    ambiguity_pairs: list[dict[str, Any]] = []
    counterfactual_pairs: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []

    # Use early episodes as detailed episodes. Paired worlds share a canonical observable prefix.
    pair_start = spec.scale.outcomes - (spec.scale.ambiguity_pairs * 2) + 1
    pair_episode_ids = [f"EP-{i:06d}" for i in range(pair_start, spec.scale.outcomes + 1)]
    if not service_paths:
        raise RuntimeError("No service has both a routed-through dependency and a vendor dependency")
    for pair_index in range(spec.scale.ambiguity_pairs):
        ep_a, ep_b = pair_episode_ids[pair_index * 2 : pair_index * 2 + 2]
        if ep_b not in incident_by_episode:
            break
        pair_id = f"AMB-{pair_index+1:03d}"
        service_id, infra_id, vendor_id = service_paths[pair_index % len(service_paths)]
        family_a = "SECURE_GATEWAY_POLICY" if pair_index % 2 == 0 else "IDENTITY_DEGRADATION"
        family_b = "EXTERNAL_VENDOR_OUTAGE" if pair_index % 2 == 0 else "CERTIFICATE_EXPIRY"
        pattern_a = patterns_by_family[family_a][pair_index % len(patterns_by_family[family_a])]
        pattern_b = patterns_by_family[family_b][pair_index % len(patterns_by_family[family_b])]
        base_inc = incident_by_episode[ep_a]
        base_obs = observation_by_episode[ep_a]
        shared_opened = datetime.fromisoformat(base_inc["opened_at"])
        shared_metric = "saas_connection_failure_rate" if pair_index % 2 == 0 else "authentication_failure_rate"
        shared_symptom = "cross-platform access failure" if pair_index % 2 == 0 else "authentication failure"
        shared_severity = "HIGH"
        shared_region = entity_by_id[service_id]["region"]
        shared_bu = entity_by_id[service_id]["business_unit"]
        shared_team = owners.get(service_id, base_inc["support_team_id"])
        for ep in (ep_a, ep_b):
            inc = incident_by_episode[ep]
            inc.update({
                "entity_id": service_id,
                "entity_type": "APPLICATION_SERVICE",
                "opened_at": shared_opened.isoformat(),
                "region": shared_region,
                "business_unit": shared_bu,
                "severity": shared_severity,
                "symptom_category": shared_symptom,
                "onset_shape": "STEP",
                "blast_radius_band": "CROSS_PLATFORM",
                "support_team_id": shared_team,
                "recent_change_present": False,
                "vendor_status_at_onset": "UNKNOWN",
                "short_description": f"Cross-platform access failures affecting {entity_by_id[service_id]['name']}",
            })
            obs = observation_by_episode[ep]
            obs.update({
                "entity_id": service_id,
                "metric_id": shared_metric,
                "breach_direction": "UP",
                "observed_at": (shared_opened - timedelta(minutes=9)).isoformat(),
                "severity": shared_severity,
                "value_band": "SEVERE",
            })
        # Align private truth and eventual outcomes with the intervened causes.
        for ep, family, pattern, true_root in [
            (ep_a, family_a, pattern_a, infra_id),
            (ep_b, family_b, pattern_b, vendor_id if family_b == "EXTERNAL_VENDOR_OUTAGE" else infra_id),
        ]:
            truth_row = truth_by_episode[ep]
            truth_row.update({
                "true_cause_family": family,
                "true_root_entity_id": true_root,
                "true_pattern_id": pattern["known_error_id"],
                "correct_remediation": pattern["recommended_action"],
                "propagation_targets": [service_id],
                "counterfactual_family_id": pair_id,
                "background_stream": f"background:{pair_id}",
            })
            out = outcome_by_episode[ep]
            out.update({
                "known_error_id": pattern["known_error_id"],
                "scenario_pattern": family,
                "entity_id": service_id,
                "recommendation": pattern["recommended_action"],
                "approval_decision": "APPROVED",
                "human_modification": "",
                "action_performed": pattern["recommended_action"],
                "outcome": "RESOLVED",
                "recurrence_within_24h": False,
                "recovery_minutes": 42 if ep == ep_a else 55,
            })
        shared_prefix_until = shared_opened + timedelta(minutes=18)
        prefix_a: list[dict[str, Any]] = []
        prefix_b: list[dict[str, Any]] = []
        for minute in [0, 5, 10, 15]:
            value = round(0.55 + 0.12 * stable_float(spec.seed, "ambiguity-prefix", pair_id, minute), 4)
            for ep, prefix in [(ep_a, prefix_a), (ep_b, prefix_b)]:
                row = {
                    "telemetry_id": f"TEL-{ep}-{minute:03d}",
                    "episode_id": ep,
                    "entity_id": service_id,
                    "metric_id": shared_metric,
                    "observed_at": (shared_opened + timedelta(minutes=minute)).isoformat(),
                    "value": value,
                    "phase": "PRE_REVEAL",
                    "data_classification": spec.data_classification,
                }
                telemetry.append(row)
                prefix.append({k: row[k] for k in ["metric_id", "value", "phase"]})
        if prefix_a != prefix_b:
            raise AssertionError(f"Ambiguity prefix mismatch for {pair_id}")
        prefix_hash = hashlib.sha256(json.dumps(prefix_a, sort_keys=True).encode()).hexdigest()
        for ep, family in [(ep_a, family_a), (ep_b, family_b)]:
            reveal_type = "INTERNAL_PATH_EVIDENCE" if family in {"SECURE_GATEWAY_POLICY", "IDENTITY_DEGRADATION"} else "AUTHORITATIVE_VENDOR_INCIDENT"
            runtime_events.append({
                "event_id": f"EVT-{ep}-REVEAL",
                "episode_id": ep,
                "signal_type": reveal_type,
                "observed_at": (shared_prefix_until + timedelta(minutes=1)).isoformat(),
                "available_at": (shared_prefix_until + timedelta(minutes=4)).isoformat(),
                "ingested_at": (shared_prefix_until + timedelta(minutes=5)).isoformat(),
                "resolves_flags": ["AMBIGUOUS_CAUSE"],
                "source_authority": "AUTHORITATIVE",
                "data_classification": spec.data_classification,
            })
            for minute in [20, 25, 30]:
                base = 0.72 if reveal_type == "INTERNAL_PATH_EVIDENCE" else 0.83
                telemetry.append({
                    "telemetry_id": f"TEL-{ep}-{minute:03d}",
                    "episode_id": ep,
                    "entity_id": service_id,
                    "metric_id": shared_metric,
                    "observed_at": (shared_opened + timedelta(minutes=minute)).isoformat(),
                    "value": round(base + 0.08 * stable_float(spec.seed, "ambiguity-post", ep, minute), 4),
                    "phase": "POST_REVEAL",
                    "data_classification": spec.data_classification,
                })
        ambiguity_pairs.append({
            "ambiguity_family_id": pair_id,
            "episode_a": ep_a,
            "episode_b": ep_b,
            "cause_a": family_a,
            "cause_b": family_b,
            "shared_trigger_entity_id": service_id,
            "root_a": infra_id,
            "root_b": vendor_id if family_b == "EXTERNAL_VENDOR_OUTAGE" else infra_id,
            "shared_prefix_until": shared_prefix_until.isoformat(),
            "canonical_prefix_hash": prefix_hash,
            "expected_pre_reveal_disposition": "GOVERNED_UNCERTAINTY",
            "expected_post_reveal_divergence": True,
        })
        if pair_index < spec.scale.counterfactual_pairs:
            counterfactual_pairs.append({
                "counterfactual_pair_id": f"CF-{pair_index+1:03d}",
                "factual_episode_id": ep_a,
                "counterfactual_episode_id": ep_b,
                "fixed_topology": True,
                "fixed_background_stream": f"background:{pair_id}",
                "intervention": f"do(cause={family_b})",
                "changed_descendants": ["cause_dependent_telemetry", "distinguishing_evidence", "action_effectiveness", "outcome"],
            })

    # Additional detailed telemetry for non-paired episodes.
    detailed_ids = sorted(set(r["episode_id"] for r in history["detailed_ids"]) | set(pair_episode_ids))
    paired = set(pair_episode_ids)
    for ep in detailed_ids:
        if ep in paired or ep not in incident_by_episode:
            continue
        opened = datetime.fromisoformat(incident_by_episode[ep]["opened_at"])
        for minute in range(-10, 61, 5):
            phase = "BASELINE" if minute < 0 else ("DEGRADED" if minute < 35 else "RECOVERY")
            baseline = 0.2 if phase == "BASELINE" else (0.75 if phase == "DEGRADED" else 0.35)
            telemetry.append({
                "telemetry_id": f"TEL-{ep}-{minute+10:03d}",
                "episode_id": ep,
                "entity_id": incident_by_episode[ep]["entity_id"],
                "metric_id": observation_by_episode[ep]["metric_id"],
                "observed_at": (opened + timedelta(minutes=minute)).isoformat(),
                "value": round(baseline + 0.12 * stable_float(spec.seed, "telemetry", ep, minute), 4),
                "phase": phase,
                "data_classification": spec.data_classification,
            })

    # Private causal lineage for every paired episode and a sample of detailed episodes.
    for ep in detailed_ids:
        if ep not in truth_by_episode:
            continue
        lineage.append({
            "episode_id": ep,
            "field": "ambient_workload",
            "causal_parents": [],
            "generation_mechanism": "AMBIENT_LOAD",
            "exogenous_stream": truth_by_episode[ep]["background_stream"],
            "counterfactual_descendant": False,
        })
        lineage.append({
            "episode_id": ep,
            "field": "cause_dependent_telemetry",
            "causal_parents": ["true_cause_family", "topology"],
            "generation_mechanism": "FAULT_PROPAGATION",
            "exogenous_stream": f"propagation:{ep}",
            "counterfactual_descendant": True,
        })

    return {
        "telemetry": telemetry,
        "runtime_events": runtime_events,
        "ambiguity_pairs": ambiguity_pairs,
        "counterfactual_pairs": counterfactual_pairs,
        "lineage": lineage,
    }


def generate_documents(spec: GeneratorSpec, patterns: list[dict[str, Any]], history: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    docs: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    doc_types = ["KNOWLEDGE_ARTICLE", "RUNBOOK", "PROBLEM_RECORD", "POST_INCIDENT_REVIEW", "ARCHITECTURE", "VENDOR_ADVISORY", "WIKI"]
    incidents = history["incidents"]
    outcomes = history["outcomes"]
    for i in range(spec.scale.source_documents):
        doc_id = f"DOC-{i+1:05d}"
        pattern = patterns[i % len(patterns)]
        incident = incidents[(i * 19) % len(incidents)]
        outcome = outcomes[(i * 19) % len(outcomes)]
        doc_type = doc_types[i % len(doc_types)]
        incident_time = datetime.fromisoformat(incident["opened_at"])
        if doc_type == "POST_INCIDENT_REVIEW":
            published = datetime.fromisoformat(outcome["recorded_at"]) + timedelta(days=2)
        elif doc_type == "VENDOR_ADVISORY":
            published = incident_time + timedelta(minutes=25)
        else:
            published = incident_time - timedelta(days=30 + (i % 300))
        trust = "TRUSTED" if i % 8 else "CONDITIONAL"
        title = f"{doc_type.replace('_', ' ').title()}: {pattern['cause_family'].replace('_', ' ').title()}"
        base_text = (
            f"This synthetic {doc_type.lower().replace('_', ' ')} describes {pattern['symptom_category']} "
            f"for entity {pattern['applies_to_entity_id']}. The governed diagnostic metric is "
            f"{pattern['trigger_metric_id']} with breach direction {pattern['breach_direction']}. "
            f"The recommended controlled action is {pattern['recommended_action']}. "
            f"For incident {incident['incident_id']}, approval was {outcome['approval_decision']} and "
            f"the recorded result was {outcome['outcome']}. This material is synthetic and must not be "
            f"treated as a live operational instruction."
        )
        docs.append({
            "document_id": doc_id,
            "document_type": doc_type,
            "title": title,
            "entity_ids": [pattern["applies_to_entity_id"], incident["entity_id"]],
            "known_error_ids": [pattern["known_error_id"]],
            "incident_ids": [incident["incident_id"]] if doc_type in {"POST_INCIDENT_REVIEW", "PROBLEM_RECORD"} else [],
            "symptom_categories": [pattern["symptom_category"]],
            "published_at": published.isoformat(),
            "last_validated_at": (published + timedelta(days=20)).isoformat(),
            "trust_level": trust,
            "content": base_text,
            "data_classification": spec.data_classification,
        })
    # Exactly requested chunks, distributed as evenly as possible.
    base_chunks = spec.scale.document_chunks // spec.scale.source_documents
    remainder = spec.scale.document_chunks % spec.scale.source_documents
    for i, doc in enumerate(docs):
        count = base_chunks + (1 if i < remainder else 0)
        for c in range(count):
            chunk_id = f"CHUNK-{len(chunks)+1:06d}"
            chunks.append({
                "chunk_id": chunk_id,
                "document_id": doc["document_id"],
                "chunk_index": c,
                "document_type": doc["document_type"],
                "published_at": doc["published_at"],
                "trust_level": doc["trust_level"],
                "entity_ids": doc["entity_ids"],
                "known_error_ids": doc["known_error_ids"],
                "text": f"{doc['content']} Section {c+1} adds governed context, evidence provenance, temporal availability, and validation steps.",
                "data_classification": spec.data_classification,
            })
    assert len(chunks) == spec.scale.document_chunks
    return docs, chunks


def generate_vendor_advisories(spec: GeneratorSpec, entities: list[dict[str, Any]], history: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    vendors = [r for r in entities if r["entity_type"] == "EXTERNAL_VENDOR_SERVICE"]
    incidents = history["incidents"]
    rows: list[dict[str, Any]] = []
    count = max(50, min(1000, spec.scale.incidents // 50))
    for i in range(count):
        vendor = vendors[i % len(vendors)]
        incident = incidents[(i * 37) % len(incidents)]
        incident_time = datetime.fromisoformat(incident["opened_at"])
        status = "DEGRADED" if i % 7 == 0 else "HEALTHY"
        rows.append({
            "advisory_id": f"ADV-{i+1:05d}",
            "vendor_entity_id": vendor["entity_id"],
            "status": status,
            "incident_confirmed": status == "DEGRADED",
            "affected_scope": "REGIONAL" if status == "DEGRADED" else "NONE",
            "observed_at": (incident_time + timedelta(minutes=20)).isoformat(),
            "published_at": (incident_time + timedelta(minutes=25)).isoformat(),
            "source_authority": "AUTHORITATIVE",
            "source_reference": f"synthetic://vendor/{vendor['entity_id']}/{i+1}",
            "confidence": 0.98,
            "data_classification": spec.data_classification,
        })
    return rows


def write_schemas(root: Path) -> None:
    schemas = {
        "entity": {"required": ["entity_id", "entity_type", "name", "data_classification"]},
        "relationship": {"required": ["relationship_id", "source_entity_id", "relationship_type", "target_entity_id"]},
        "incident": {"required": ["incident_id", "episode_id", "entity_id", "opened_at", "symptom_category"]},
        "outcome": {"required": ["outcome_id", "incident_id", "known_error_id", "approval_decision", "outcome"]},
        "document_chunk": {"required": ["chunk_id", "document_id", "text", "published_at"]},
    }
    for name, schema in schemas.items():
        write_json(root / "schemas" / f"{name}.schema.json", schema)


def generate_dataset(spec: GeneratorSpec, output: Path) -> dict[str, Any]:
    paths = ensure_dirs(output)
    entities = generate_entities(spec)
    relationships = generate_relationships(spec, entities)
    patterns = generate_patterns(spec, entities)
    history = generate_operational_history(spec, entities, relationships, patterns)
    temporal = generate_ambiguity_and_telemetry(spec, entities, relationships, patterns, history)
    documents, chunks = generate_documents(spec, patterns, history)
    advisories = generate_vendor_advisories(spec, entities, history)

    counts: dict[str, int] = {}
    counts["entities"] = write_csv(paths["observable"] / "entities.csv", entities, list(entities[0].keys()))
    counts["relationships"] = write_csv(paths["observable"] / "semantic_relationships.csv", relationships, list(relationships[0].keys()))
    counts["known_errors"] = write_csv(paths["observable"] / "known_errors.csv", patterns, list(patterns[0].keys()))
    counts["incidents"] = write_csv(paths["observable"] / "incidents.csv", history["incidents"], list(history["incidents"][0].keys()))
    counts["health_observations"] = write_csv(paths["observable"] / "health_observations.csv", history["observations"], list(history["observations"][0].keys()))
    counts["changes"] = write_csv(paths["observable"] / "changes.csv", history["changes"], list(history["changes"][0].keys()) if history["changes"] else ["change_id"])
    counts["outcomes"] = write_csv(paths["observable"] / "outcome_history.csv", history["outcomes"], list(history["outcomes"][0].keys()))
    counts["telemetry_samples"] = write_jsonl(paths["observable"] / "telemetry_samples.jsonl", temporal["telemetry"])
    counts["runtime_evidence_events"] = write_jsonl(paths["observable"] / "runtime_evidence_events.jsonl", temporal["runtime_events"])
    counts["documents"] = write_jsonl(paths["observable"] / "knowledge_documents.jsonl", documents)
    counts["document_chunks"] = write_jsonl(paths["observable"] / "document_chunks.jsonl", chunks)
    counts["vendor_advisories"] = write_jsonl(paths["observable"] / "vendor_advisories.jsonl", advisories)
    counts["ground_truth_episodes"] = write_csv(paths["truth"] / "ground_truth_episodes.csv", history["truth"], list(history["truth"][0].keys()))
    counts["ambiguity_pairs"] = write_csv(paths["truth"] / "ambiguity_pairs.csv", temporal["ambiguity_pairs"], list(temporal["ambiguity_pairs"][0].keys()) if temporal["ambiguity_pairs"] else ["ambiguity_family_id"])
    counts["counterfactual_pairs"] = write_csv(paths["truth"] / "counterfactual_pairs.csv", temporal["counterfactual_pairs"], list(temporal["counterfactual_pairs"][0].keys()) if temporal["counterfactual_pairs"] else ["counterfactual_pair_id"])
    counts["causal_lineage"] = write_jsonl(paths["truth"] / "causal_lineage.jsonl", temporal["lineage"])
    write_schemas(output)

    files = [p for p in output.rglob("*") if p.is_file() and p.name != "manifest.json"]
    manifest = {
        "generator_version": "1.0.0",
        "schema_version": spec.schema_version,
        "enterprise_name": spec.name,
        "seed": spec.seed,
        "generated_at": datetime.now(UTC).isoformat(),
        "data_classification": spec.data_classification,
        "counts": counts,
        "policy": {
            "minimum_outcome_sample": spec.minimum_outcome_sample,
            "transfer_ceiling": spec.transfer_ceiling,
            "prior_confidence_strategy": spec.prior_confidence_strategy,
        },
        "checksums": {str(p.relative_to(output)): sha256_file(p) for p in files},
    }
    write_json(output / "manifest.json", manifest)
    return manifest
