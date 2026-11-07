import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "local_data" / "pattern_registry.sqlite3"

def initialize():
    DB.parent.mkdir(exist_ok=True)

    with sqlite3.connect(DB) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS patterns (
                pattern_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                name TEXT NOT NULL,
                mechanism TEXT NOT NULL,
                applicability_json TEXT NOT NULL,
                required_checks_json TEXT NOT NULL,
                exclusions_json TEXT NOT NULL,
                available_at TEXT NOT NULL,
                PRIMARY KEY (pattern_id, version)
            );

            CREATE TABLE IF NOT EXISTS episodes (
                episode_id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                pattern_id TEXT NOT NULL,
                pattern_version INTEGER NOT NULL,
                outcome TEXT NOT NULL CHECK (
                    outcome IN ('SUPPORTING', 'CONTRADICTORY', 'INCONCLUSIVE')
                ),
                evidence_refs_json TEXT NOT NULL,
                rationale TEXT NOT NULL,
                reviewed_by TEXT NOT NULL,
                available_at TEXT NOT NULL,
                synthetic INTEGER NOT NULL CHECK (synthetic IN (0, 1)),
                UNIQUE (incident_id, pattern_id, pattern_version),
                FOREIGN KEY (pattern_id, pattern_version)
                    REFERENCES patterns(pattern_id, version)
            );

            CREATE TABLE IF NOT EXISTS assessments (
                assessment_id TEXT PRIMARY KEY,
                pattern_id TEXT NOT NULL,
                pattern_version INTEGER NOT NULL,
                assessed_at TEXT NOT NULL,
                evidence_cutoff TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                readiness TEXT NOT NULL CHECK (
                    readiness IN (
                        'CANDIDATE', 'FAST_PASS_ELIGIBLE', 'SUSPENDED'
                    )
                ),
                supporting_count INTEGER NOT NULL,
                contradictory_count INTEGER NOT NULL,
                inconclusive_count INTEGER NOT NULL,
                rationale TEXT NOT NULL,
                FOREIGN KEY (pattern_id, pattern_version)
                    REFERENCES patterns(pattern_id, version)
            );
        """)

        tables = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' ORDER BY name"
        ).fetchall()

    print("Registry initialized:", DB)
    print("Tables:", ", ".join(row[0] for row in tables))
    print("No patterns seeded; no readiness decisions made.")

if __name__ == "__main__":
    initialize()
