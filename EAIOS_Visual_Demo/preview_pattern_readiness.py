import sqlite3
from eaios_pattern_registry import DB

def assess(connection, cutoff):
    rows = connection.execute("""
        SELECT outcome
        FROM episodes
        WHERE pattern_id = ?
          AND pattern_version = ?
          AND available_at <= ?
    """, ("PAT-CONNECTOR-EXHAUSTION", 1, cutoff)).fetchall()

    counts = {
        outcome: sum(row[0] == outcome for row in rows)
        for outcome in ("SUPPORTING", "CONTRADICTORY", "INCONCLUSIVE")
    }

    if counts["CONTRADICTORY"]:
        readiness = "SUSPENDED"
        reason = (
            "Contradictory history requires applicability review. "
            "Earlier supporting episodes remain preserved."
        )
    else:
        readiness = "CANDIDATE"
        reason = (
            "Supporting history exists, but these fixtures lack "
            "verifiable evidence references. Fast Pass is not established."
        )

    return readiness, counts, reason

with sqlite3.connect(DB) as connection:
    before = assess(connection, "2026-07-06 00:00:00")
    after = assess(connection, "2026-07-09 00:00:00")

assert before[1]["SUPPORTING"] == 2
assert before[1]["CONTRADICTORY"] == 0
assert before[0] == "CANDIDATE"
assert after[1]["SUPPORTING"] == 2
assert after[1]["CONTRADICTORY"] == 1
assert after[0] == "SUSPENDED"

for label, result in [
    ("Before contradiction was available", before),
    ("After contradiction was available", after),
]:
    readiness, counts, reason = result
    print(f"\n{label}")
    print("Readiness:", readiness)
    print("History:", counts)
    print("Reason:", reason)

print("\nPASS: cutoff filtering and conservative readiness checks.")
print("Read-only preview; no assessments saved. No AWS calls.")
