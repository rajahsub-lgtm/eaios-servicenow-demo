from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeClassifier

from .io_utils import write_json
from .spec import GeneratorSpec


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _check(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def validate_dataset(spec: GeneratorSpec, dataset: Path) -> dict[str, Any]:
    observable = dataset / "observable"
    truth_dir = dataset / "private_truth"
    reports = dataset / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    warnings: list[str] = []

    entities = _read_csv(observable / "entities.csv")
    relationships = _read_csv(observable / "semantic_relationships.csv")
    patterns = _read_csv(observable / "known_errors.csv")
    incidents = _read_csv(observable / "incidents.csv")
    observations = _read_csv(observable / "health_observations.csv")
    changes = _read_csv(observable / "changes.csv")
    outcomes = _read_csv(observable / "outcome_history.csv")
    telemetry = _read_jsonl(observable / "telemetry_samples.jsonl")
    runtime_events = _read_jsonl(observable / "runtime_evidence_events.jsonl")
    documents = _read_jsonl(observable / "knowledge_documents.jsonl")
    chunks = _read_jsonl(observable / "document_chunks.jsonl")
    truth = _read_csv(truth_dir / "ground_truth_episodes.csv")
    ambiguity = _read_csv(truth_dir / "ambiguity_pairs.csv")
    counterfactual = _read_csv(truth_dir / "counterfactual_pairs.csv")

    # Exact scale and uniqueness.
    expected_counts = {
        "entities": spec.scale.entities,
        "relationships": spec.scale.relationships,
        "known_errors": spec.scale.patterns,
        "incidents": spec.scale.incidents,
        "outcomes": spec.scale.outcomes,
        "documents": spec.scale.source_documents,
        "document_chunks": spec.scale.document_chunks,
        "ambiguity_pairs": spec.scale.ambiguity_pairs,
        "counterfactual_pairs": spec.scale.counterfactual_pairs,
    }
    actual_counts = {
        "entities": len(entities), "relationships": len(relationships), "known_errors": len(patterns),
        "incidents": len(incidents), "outcomes": len(outcomes), "documents": len(documents),
        "document_chunks": len(chunks), "ambiguity_pairs": len(ambiguity), "counterfactual_pairs": len(counterfactual),
    }
    for name, expected in expected_counts.items():
        _check(actual_counts[name] == expected, f"{name}: expected {expected}, found {actual_counts[name]}", errors)

    id_specs = [
        (entities, "entity_id"), (relationships, "relationship_id"), (patterns, "known_error_id"),
        (incidents, "incident_id"), (observations, "observation_id"), (outcomes, "outcome_id"),
        (documents, "document_id"), (chunks, "chunk_id"),
    ]
    for rows, key in id_specs:
        ids = [row[key] for row in rows]
        _check(len(ids) == len(set(ids)), f"Duplicate {key} values", errors)

    entity_ids = {r["entity_id"] for r in entities}
    pattern_ids = {r["known_error_id"] for r in patterns}
    incident_ids = {r["incident_id"] for r in incidents}
    episode_ids = {r["episode_id"] for r in incidents}
    doc_ids = {r["document_id"] for r in documents}

    # Referential integrity.
    for edge in relationships:
        _check(edge["source_entity_id"] in entity_ids, f"Missing relationship source {edge['source_entity_id']}", errors)
        _check(edge["target_entity_id"] in entity_ids, f"Missing relationship target {edge['target_entity_id']}", errors)
    for row in incidents:
        _check(row["entity_id"] in entity_ids, f"Incident {row['incident_id']} references missing entity", errors)
    for row in outcomes:
        _check(row["incident_id"] in incident_ids, f"Outcome {row['outcome_id']} references missing incident", errors)
        _check(row["known_error_id"] in pattern_ids, f"Outcome {row['outcome_id']} references missing pattern", errors)
    for chunk in chunks:
        _check(chunk["document_id"] in doc_ids, f"Chunk {chunk['chunk_id']} references missing document", errors)
    _check({r["episode_id"] for r in truth} == episode_ids, "Ground truth does not cover exactly all episodes", errors)

    # Synthetic classification and circularity prevention.
    classified_sets = [entities, relationships, patterns, incidents, observations, outcomes, documents, chunks]
    for rows in classified_sets:
        _check(all(r.get("data_classification") == "SYNTHETIC" for r in rows), "Non-synthetic classification found", errors)
    _check(all(not r.get("prior_confidence") for r in outcomes), "Generated outcome contains prior_confidence", errors)

    # Temporal integrity.
    incident_by_id = {r["incident_id"]: r for r in incidents}
    observation_by_id = {r["observation_id"]: r for r in observations}
    change_by_id = {r["change_id"]: r for r in changes if r.get("change_id")}
    truth_by_episode = {r["episode_id"]: r for r in truth}
    for inc in incidents:
        obs = observation_by_id[inc["observation_id"]]
        _check(_dt(obs["observed_at"]) <= _dt(inc["opened_at"]), f"Observation after incident {inc['incident_id']}", errors)
    for out in outcomes:
        inc = incident_by_id[out["incident_id"]]
        _check(_dt(out["recorded_at"]) >= _dt(inc["opened_at"]), f"Outcome precedes incident {out['incident_id']}", errors)
        if out["approval_decision"] == "REJECTED":
            _check(not out["action_performed"], f"Rejected outcome executed action {out['outcome_id']}", errors)
        if out["recurrence_within_24h"].lower() == "true":
            _check(out["outcome"] == "RESOLVED", f"Recurrence on unresolved outcome {out['outcome_id']}", errors)
    for t in truth:
        change_id = t.get("change_id", "")
        if change_id:
            inc = incident_by_id[t["incident_id"]]
            _check(_dt(change_by_id[change_id]["implemented_at"]) < _dt(inc["opened_at"]), f"Change not before incident {t['incident_id']}", errors)
    outcome_by_incident = {r["incident_id"]: r for r in outcomes}
    for doc in documents:
        if doc["document_type"] == "POST_INCIDENT_REVIEW" and doc.get("incident_ids"):
            incident_ref = doc["incident_ids"][0]
            _check(_dt(doc["published_at"]) > _dt(outcome_by_incident[incident_ref]["recorded_at"]), f"PIR published before outcome for {incident_ref}", errors)

    # Long-tailed experience.
    counts = Counter(r["known_error_id"] for r in outcomes)
    distribution = {
        "zero": sum(1 for p in pattern_ids if counts[p] == 0),
        "one_to_four": sum(1 for p in pattern_ids if 1 <= counts[p] <= 4),
        "five_to_fourteen": sum(1 for p in pattern_ids if 5 <= counts[p] <= 14),
        "fifteen_to_ninety_nine": sum(1 for p in pattern_ids if 15 <= counts[p] <= 99),
        "hundred_plus": sum(1 for p in pattern_ids if counts[p] >= 100),
        "max_cases": max(counts.values()) if counts else 0,
    }
    _check(distribution["zero"] >= max(2, spec.scale.patterns // 12), "Too few documentation-only patterns", errors)
    _check(distribution["one_to_four"] >= max(2, spec.scale.patterns // 10), "Sparse pattern tail missing", errors)
    _check(distribution["five_to_fourteen"] >= max(2, spec.scale.patterns // 10), "Emerging pattern band missing", errors)
    _check(distribution["max_cases"] >= max(50, spec.scale.outcomes // 20), "No dominant long-tail head", errors)

    # Topology integrity for ambiguity pairs and exact prefix equality.
    edge_set = {(r["source_entity_id"], r["relationship_type"], r["target_entity_id"]) for r in relationships}
    telemetry_by_episode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in telemetry:
        telemetry_by_episode[row["episode_id"]].append(row)
    event_by_episode = {r["episode_id"]: r for r in runtime_events}
    for pair in ambiguity:
        ep_a, ep_b = pair["episode_a"], pair["episode_b"]
        prefix_a = [
            {k: r[k] for k in ["metric_id", "value", "phase"]}
            for r in sorted(telemetry_by_episode[ep_a], key=lambda x: x["observed_at"])
            if r["phase"] == "PRE_REVEAL"
        ]
        prefix_b = [
            {k: r[k] for k in ["metric_id", "value", "phase"]}
            for r in sorted(telemetry_by_episode[ep_b], key=lambda x: x["observed_at"])
            if r["phase"] == "PRE_REVEAL"
        ]
        _check(prefix_a == prefix_b, f"Ambiguity pair {pair['ambiguity_family_id']} prefix differs", errors)
        prefix_hash = __import__("hashlib").sha256(json.dumps(prefix_a, sort_keys=True).encode()).hexdigest()
        _check(prefix_hash == pair["canonical_prefix_hash"], f"Ambiguity pair {pair['ambiguity_family_id']} hash mismatch", errors)
        service, root_a, root_b = pair["shared_trigger_entity_id"], pair["root_a"], pair["root_b"]
        _check((service, "ROUTED_THROUGH", root_a) in edge_set or root_a == root_b, f"Ambiguity pair {pair['ambiguity_family_id']} lacks internal topology", errors)
        _check((service, "DEPENDS_ON", root_b) in edge_set or root_a == root_b, f"Ambiguity pair {pair['ambiguity_family_id']} lacks vendor topology", errors)
        _check(ep_a in event_by_episode and ep_b in event_by_episode, f"Ambiguity pair {pair['ambiguity_family_id']} lacks reveal events", errors)
        if ep_a in event_by_episode:
            _check(_dt(event_by_episode[ep_a]["available_at"]) > _dt(pair["shared_prefix_until"]), f"Reveal available before ambiguity window {pair['ambiguity_family_id']}", errors)

    # Counterfactual invariants.
    for pair in counterfactual:
        a = truth_by_episode[pair["factual_episode_id"]]
        b = truth_by_episode[pair["counterfactual_episode_id"]]
        _check(a["background_stream"] == b["background_stream"] == pair["fixed_background_stream"], f"Counterfactual background reseeded {pair['counterfactual_pair_id']}", errors)
        _check(a["true_cause_family"] != b["true_cause_family"], f"Counterfactual cause unchanged {pair['counterfactual_pair_id']}", errors)

    adversarial = _adversarial_probe(incidents, observations, truth, spec)
    if adversarial["decision_tree_accuracy"] > spec.trivial_classifier_max_accuracy:
        errors.append(
            f"Trivial decision tree accuracy {adversarial['decision_tree_accuracy']:.3f} exceeds "
            f"{spec.trivial_classifier_max_accuracy:.3f}"
        )
    if adversarial["logistic_accuracy"] > spec.trivial_classifier_max_accuracy:
        warnings.append(
            f"Logistic probe accuracy {adversarial['logistic_accuracy']:.3f} exceeds configured ceiling; inspect feature shortcuts"
        )

    report = {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "counts": actual_counts,
        "experience_distribution": distribution,
        "adversarial": adversarial,
        "invariants": {
            "prior_confidence_omitted": all(not r.get("prior_confidence") for r in outcomes),
            "ambiguity_prefixes_identical": not any("prefix differs" in e for e in errors),
            "counterfactual_background_fixed": not any("background reseeded" in e for e in errors),
            "hidden_truth_separate": (truth_dir / "ground_truth_episodes.csv").exists(),
        },
    }
    write_json(reports / "validation_report.json", report)
    write_json(reports / "adversarial_validation.json", adversarial)
    (reports / "VALIDATION_SUMMARY.txt").write_text(
        f"Status: {report['status']}\nErrors: {len(errors)}\nWarnings: {len(warnings)}\n"
        f"Decision tree accuracy: {adversarial['decision_tree_accuracy']:.3f}\n"
        f"Logistic accuracy: {adversarial['logistic_accuracy']:.3f}\n",
        encoding="utf-8",
    )
    return report


def _adversarial_probe(incidents: list[dict[str, str]], observations: list[dict[str, str]], truth: list[dict[str, str]], spec: GeneratorSpec) -> dict[str, Any]:
    inc = pd.DataFrame(incidents)
    obs = pd.DataFrame(observations)[["episode_id", "metric_id", "breach_direction", "value_band"]]
    gt = pd.DataFrame(truth)[["episode_id", "true_cause_family"]]
    df = inc.merge(obs, on="episode_id", how="inner").merge(gt, on="episode_id", how="inner")
    features = [
        "entity_type", "region", "business_unit", "severity", "symptom_category", "onset_shape",
        "blast_radius_band", "recent_change_present", "vendor_status_at_onset", "metric_id",
        "breach_direction", "value_band",
    ]
    X = df[features].astype(str)
    y = df["true_cause_family"].astype(str)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=spec.seed % (2**32 - 1), stratify=y
    )
    encoder = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), features)])
    tree = Pipeline([("encode", encoder), ("model", DecisionTreeClassifier(max_depth=4, min_samples_leaf=50, random_state=17))])
    logit = Pipeline([("encode", encoder), ("model", LogisticRegression(max_iter=250, C=0.4))])
    majority = float(y_test.value_counts(normalize=True).iloc[0])
    tree.fit(X_train, y_train)
    tree_pred = tree.predict(X_test)
    logit.fit(X_train, y_train)
    logit_pred = logit.predict(X_test)
    return {
        "rows": int(len(df)),
        "target_classes": int(y.nunique()),
        "majority_baseline": round(majority, 4),
        "decision_tree_accuracy": round(float(accuracy_score(y_test, tree_pred)), 4),
        "decision_tree_balanced_accuracy": round(float(balanced_accuracy_score(y_test, tree_pred)), 4),
        "logistic_accuracy": round(float(accuracy_score(y_test, logit_pred)), 4),
        "logistic_balanced_accuracy": round(float(balanced_accuracy_score(y_test, logit_pred)), 4),
        "feature_set": features,
        "note": "Observable pre-decision metadata only; identifiers, outcome fields, post-reveal evidence, and private truth are excluded.",
    }
