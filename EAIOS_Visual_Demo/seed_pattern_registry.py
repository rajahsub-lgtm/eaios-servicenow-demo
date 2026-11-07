import json
import sqlite3
from eaios_pattern_registry import DB

pattern = (
    "PAT-CONNECTOR-EXHAUSTION",
    1,
    "Payment connector pool exhaustion",
    "Connector connection capacity becomes constrained, contributing "
    "to payment timeouts. Database pressure may be a cause or an effect.",
    json.dumps({
        "component_type": "payment_connector",
        "symptoms": ["high_active_connections", "payment_timeouts"],
        "context": "Connector depends on a database and payment gateway",
        "data_classification": "SYNTHETIC"
    }),
    json.dumps([
        "Verify actual pool capacity and connection wait or rejection metrics",
        "Check database transactions, locks and retry amplification",
        "Validate gateway health and protocol negotiation",
        "Review relevant changes available at the incident cutoff",
        "Check for contradictory evidence before selecting Fast Pass"
    ]),
    json.dumps([
        "Threshold breach alone does not prove pool exhaustion",
        "Missing gateway or database evidence prevents Fast Pass",
        "Unresolved material contradictions require full investigation",
        "Historical recovery alone does not prove the causal mechanism"
    ]),
    "2026-07-01 00:00:00"
)

with sqlite3.connect(DB) as connection:
    connection.execute("PRAGMA foreign_keys = ON")
    cursor = connection.execute("""
        INSERT INTO patterns (
            pattern_id, version, name, mechanism,
            applicability_json, required_checks_json,
            exclusions_json, available_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(pattern_id, version) DO NOTHING
    """, pattern)

    print("Pattern inserted." if cursor.rowcount else
          "Pattern version already exists; left unchanged.")

    row = connection.execute("""
        SELECT pattern_id, version, name
        FROM patterns
        WHERE pattern_id = ? AND version = ?
    """, pattern[:2]).fetchone()

    print("Stored pattern:", row)
    print("No episodes or readiness assessments added.")
    print("Availability date is a synthetic historical fixture.")


