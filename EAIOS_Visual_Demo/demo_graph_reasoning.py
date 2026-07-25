from pathlib import Path
import json
from graph_engine import SemanticGraph

ROOT = Path(__file__).resolve().parent
GRAPH = SemanticGraph.from_json_directory(ROOT / "json")

def require_one(steps, description):
    if len(steps) != 1:
        raise RuntimeError(f"Expected one {description}; found {len(steps)}")
    return steps[0]

def payment_business_impact_path():
    path = []
    observes = require_one(GRAPH.follow("OBS-PAY-006", predicate="OBSERVES", direction="out", allowed_authorities={"OBSERVED"}), "OBSERVES edge")
    path.append(observes)
    depends_on = require_one(GRAPH.follow(observes.to_entity_id, predicate="DEPENDS_ON", direction="in", allowed_authorities={"AUTHORITATIVE"}), "incoming DEPENDS_ON edge")
    path.append(depends_on)
    supports = require_one(GRAPH.follow(depends_on.to_entity_id, predicate="SUPPORTS", direction="out", allowed_authorities={"AUTHORITATIVE"}), "SUPPORTS edge")
    path.append(supports)
    enables = GRAPH.follow(supports.to_entity_id, predicate="ENABLES", direction="out", allowed_authorities={"AUTHORITATIVE"})
    checkout = next(step for step in enables if step.to_entity_id == "CAP-CHECKOUT")
    path.append(checkout)
    contributes = require_one(GRAPH.follow(checkout.to_entity_id, predicate="CONTRIBUTES_TO", direction="out", allowed_authorities={"AUTHORITATIVE"}), "CONTRIBUTES_TO edge")
    path.append(contributes)
    return path

def payment_knowledge_path():
    component_step = require_one(GRAPH.follow("OBS-PAY-006", predicate="OBSERVES", direction="out", allowed_authorities={"OBSERVED"}), "OBSERVES edge")
    return GRAPH.follow(component_step.to_entity_id, predicate="APPLIES_TO", direction="in", allowed_authorities={"AUTHORITATIVE"})

def queue_blast_radius_paths():
    observation_step = require_one(GRAPH.follow("OBS-QUEUE-005", predicate="OBSERVES", direction="out", allowed_authorities={"OBSERVED"}), "queue OBSERVES edge")
    results = []
    for feeds in GRAPH.follow(observation_step.to_entity_id, predicate="FEEDS", direction="out", allowed_authorities={"AUTHORITATIVE"}):
        for implements in GRAPH.follow(feeds.to_entity_id, predicate="IMPLEMENTS", direction="out", allowed_authorities={"AUTHORITATIVE"}):
            for enables in GRAPH.follow(implements.to_entity_id, predicate="ENABLES", direction="out", allowed_authorities={"AUTHORITATIVE"}):
                results.append([observation_step, feeds, implements, enables])
    return results

def main():
    print("\n=== PAYMENT: BUSINESS IMPACT PATH ===")
    payment_path = payment_business_impact_path()
    print(GRAPH.format_path(payment_path))

    print("\n=== PAYMENT: APPLICABLE KNOWN ERRORS ===")
    applicable = payment_knowledge_path()
    for step in applicable:
        print(GRAPH.format_step(step))

    print("\n=== QUEUE: DOWNSTREAM BLAST RADIUS ===")
    queue_paths = queue_blast_radius_paths()
    for index, path in enumerate(queue_paths, start=1):
        print(f"\nPath {index}")
        print(GRAPH.format_path(path))

    result = {
        "payment_business_impact_path": [
            {
                "from": step.from_entity_id,
                "predicate": step.relationship.predicate,
                "to": step.to_entity_id,
                "traversal_direction": step.traversal_direction,
                "authority": step.relationship.authority,
                "confidence": step.relationship.confidence,
                "provenance": step.relationship.provenance,
            }
            for step in payment_path
        ],
        "payment_applicable_known_errors": [step.to_entity_id for step in applicable],
        "queue_affected_capabilities": sorted({path[-1].to_entity_id for path in queue_paths}),
    }
    output_path = ROOT / "graph_reasoning_results.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nSaved structured results to: {output_path}")

if __name__ == "__main__":
    main()
