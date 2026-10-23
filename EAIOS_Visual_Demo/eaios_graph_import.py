import json
import os
from pathlib import Path

from neo4j import GraphDatabase

BASE = Path(__file__).resolve().parent / "json"
SOURCES = {
    "entities.json": ("entity_id", "ENTITY"),
    "health_observations.json": ("observation_id", "OBSERVATION"),
    "changes.json": ("change_id", "CHANGE"),
    "known_errors.json": ("known_error_id", "KNOWN_ERROR"),
    "knowledge_documents.json": ("document_id", "KNOWLEDGE"),
}


def read(filename):
    return json.loads((BASE / filename).read_text(encoding="utf-8-sig"))


def properties(record):
    # Preserve the full source and expose simple fields for graph queries.
    props = {
        key: value
        for key, value in record.items()
        if isinstance(value, (str, int, float, bool))
    }
    props["source_json"] = json.dumps(record, sort_keys=True)
    return props


def prepare():
    nodes = []
    ids = set()

    for filename, (key, kind) in SOURCES.items():
        for record in read(filename):
            identifier = record.get(key)
            if not identifier or identifier in ids:
                raise ValueError(f"Missing or duplicate node ID: {identifier}")
            ids.add(identifier)
            props = properties(record)
            props.update(
                record_id=identifier,
                record_kind=kind,
                source_file=filename,
            )
            nodes.append({"id": identifier, "props": props})

    links = []
    link_ids = set()
    for record in read("semantic_relationships.json"):
        identifier = record.get("relationship_id")
        subject = record.get("subject_entity_id")
        target = record.get("object_entity_id")
        if not identifier or identifier in link_ids:
            raise ValueError(f"Missing or duplicate relationship ID: {identifier}")
        if subject not in ids or target not in ids:
            raise ValueError(f"Unresolved endpoints: {identifier}")
        if record.get("direction") != "OUTBOUND":
            raise ValueError(f"Unsupported direction: {identifier}")
        if not record.get("predicate"):
            raise ValueError(f"Missing predicate: {identifier}")
        link_ids.add(identifier)
        props = properties(record)
        props["source_file"] = "semantic_relationships.json"
        links.append({
            "id": identifier, "subject": subject,
            "target": target, "props": props,
        })

    return nodes, links


def import_records(tx, nodes, links):
    # Reject endpoint changes rather than silently duplicating an existing edge.
    conflicts = tx.run("""
        UNWIND $rows AS row
        MATCH (a)-[r:EAIOS_LINK {relationship_id: row.id}]->(b)
        WHERE a.record_id <> row.subject OR b.record_id <> row.target
        RETURN row.id AS id
    """, rows=links).data()
    if conflicts:
        raise ValueError(f"Existing relationship endpoints differ: {conflicts}")

    tx.run("""
        UNWIND $rows AS row
        MERGE (n:EAIOSRecord {record_id: row.id})
        SET n += row.props
    """, rows=nodes).consume()

    tx.run("""
        UNWIND $rows AS row
        MATCH (a:EAIOSRecord {record_id: row.subject})
        MATCH (b:EAIOSRecord {record_id: row.target})
        MERGE (a)-[r:EAIOS_LINK {relationship_id: row.id}]->(b)
        SET r += row.props
    """, rows=links).consume()

    node_count = tx.run(
        "MATCH (n:EAIOSRecord) RETURN count(n) AS total"
    ).single()["total"]
    link_count = tx.run(
        "MATCH ()-[r:EAIOS_LINK]->() RETURN count(r) AS total"
    ).single()["total"]
    return node_count, link_count


def main():
    nodes, links = prepare()
    print(f"Validated input: {len(nodes)} nodes, {len(links)} relationships.")

    with GraphDatabase.driver(
        "bolt://localhost:7687",
        auth=("neo4j", os.environ["EAIOS_NEO4J_PASSWORD"]),
    ) as driver:
        driver.verify_connectivity()
        with driver.session(database="neo4j") as session:
            session.run("""
                CREATE CONSTRAINT eaios_record_id IF NOT EXISTS
                FOR (n:EAIOSRecord) REQUIRE n.record_id IS UNIQUE
            """).consume()
            counts = session.execute_write(import_records, nodes, links)

    print("Import committed.")
    print("Database EAIOS nodes:", counts[0])
    print("Database EAIOS relationships:", counts[1])


if __name__ == "__main__":
    main()
