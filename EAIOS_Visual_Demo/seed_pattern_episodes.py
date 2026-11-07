import json
import sqlite3
from eaios_pattern_registry import DB

episodes = [
    (
        "LAB-EP-001", "LAB-INC-001", "SUPPORTING",
        "2026-07-02 12:00:00",
        "Synthetic fixture: pool waiters and rejected connections "
        "confirmed exhaustion; gateway and database checks were normal."
    ),
    (
        "LAB-EP-002", "LAB-INC-002", "SUPPORTING",
        "2026-07-05 12:00:00",
        "Synthetic fixture: an independent incident showed the same "
        "mechanism; alternatives were investigated and not supported."
    ),
    (
        "LAB-EP-003", "LAB-INC-003", "CONTRADICTORY",
        "2026-07-08 12:00:00",
        "Synthetic fixture: similar symptoms arose from gateway "
        "protocol incompatibility; connector exhaustion was not established."
    ),
]

with sqlite3.connect(DB) as connection:
    connection.execute("PRAGMA foreign_keys = ON")

    for episode_id, incident_id, outcome, available_at, rationale in episodes:
        connection.execute("""
            INSERT INTO episodes (
                episode_id, incident_id, pattern_id, pattern_version,
                outcome, evidence_refs_json, rationale,
                reviewed_by, available_at, synthetic
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(episode_id) DO NOTHING
        """, (
            episode_id, incident_id, "PAT-CONNECTOR-EXHAUSTION", 1,
            outcome, json.dumps([]), rationale,
            "SIMULATED_REVIEWER", available_at, 1
        ))

    rows = connection.execute("""
        SELECT episode_id, outcome, available_at
        FROM episodes
        WHERE pattern_id = ? AND pattern_version = ?
        ORDER BY available_at, episode_id
    """, ("PAT-CONNECTOR-EXHAUSTION", 1)).fetchall()

for row in rows:
    print(" | ".join(row))

print("\nSynthetic fixtures only; no external evidence references.")
print("No readiness assessment or execution authorization created.")
