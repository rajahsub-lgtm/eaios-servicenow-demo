"""Load a generated enterprise for validation.

Deliberately tolerant about *what is present* and strict about *what things
mean*. A generator under development produces partial output, and a validator
that crashes on a missing file cannot report on the files that exist.

The two worlds are loaded separately and never merged. Observable evidence is
what the reasoning system may read; ground truth is what only the generator
and these validators may read. Keeping them in separate attributes means a
validator that reaches for ground truth has to say so in its own code, which
is the point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
import json


# Files the reasoning system is permitted to see.
OBSERVABLE = (
    "entities",
    "semantic_relationships",
    "known_errors",
    "outcome_history",
    "incidents",
    "problems",
    "changes",
    "knowledge_documents",
    "vendor_advisories",
    "health_observations",
    "telemetry_samples",
    "metric_definitions",
    "business_context",
    "scenarios",
    "runtime_evidence_events",
    "learned_patterns",
    "refutation_ledger",
    "runtime_outcome_feedback",
)

# Files only the generator and these validators may read. A leak of any of
# these into the observable set is a release-blocking fault, not a warning.
GROUND_TRUTH = (
    "ground_truth_episodes",
    "ground_truth_faults",
    "ground_truth_propagation",
    "ground_truth_remediation",
)

DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def parse_time(value: Any) -> datetime | None:
    """Parse a timestamp without guessing.

    Returns None rather than raising, because a malformed timestamp is a
    finding to report, not an exception to crash on — the validator should
    survive to report everything else wrong with the dataset.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(text[: len(fmt.replace("%Y", "2026"))], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    except ValueError:
        return None


@dataclass
class Dataset:
    """A generated enterprise, loaded but not interpreted."""

    root: Path
    observable: dict[str, list[dict]] = field(default_factory=dict)
    truth: dict[str, list[dict]] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)
    load_errors: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, root: str | Path) -> "Dataset":
        root = Path(root)
        dataset = cls(root=root)

        # Fixtures may sit at the root or under json/, so both layouts work
        # without the caller having to know which the generator produced.
        search = [root, root / "json"]

        for name in OBSERVABLE:
            dataset.observable[name] = dataset._read_list(search, name)
        for name in GROUND_TRUTH:
            dataset.truth[name] = dataset._read_list(
                search + [root / "ground_truth"], name
            )

        for candidate in (root / "manifest.json", root / "json" / "manifest.json"):
            if candidate.exists():
                try:
                    dataset.manifest = json.loads(
                        candidate.read_text(encoding="utf-8")
                    )
                except json.JSONDecodeError as exc:
                    dataset.load_errors.append(f"manifest.json: {exc}")
                break

        return dataset

    def _read_list(self, directories: Iterable[Path], name: str) -> list[dict]:
        for directory in directories:
            for path in (directory / f"{name}.json", directory / f"{name}.jsonl"):
                if not path.exists():
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                    if path.suffix == ".jsonl":
                        rows = [
                            json.loads(line)
                            for line in text.splitlines()
                            if line.strip()
                        ]
                    else:
                        rows = json.loads(text)
                    if not isinstance(rows, list):
                        self.load_errors.append(
                            f"{path.name}: expected a list, found "
                            f"{type(rows).__name__}"
                        )
                        return []
                    return rows
                except json.JSONDecodeError as exc:
                    self.load_errors.append(f"{path.name}: {exc}")
                    return []
        return []

    # -- convenience accessors ---------------------------------------------

    def __getitem__(self, name: str) -> list[dict]:
        return self.observable.get(name, [])

    def has(self, name: str) -> bool:
        return bool(self.observable.get(name) or self.truth.get(name))

    def ids(self, name: str, key: str) -> set[str]:
        return {
            str(row[key]) for row in self.observable.get(name, []) if row.get(key)
        }

    @property
    def entity_ids(self) -> set[str]:
        """Entities as declared. Not the graph's node population — see below."""
        return self.ids("entities", "entity_id")

    @property
    def graph_node_ids(self) -> set[str]:
        """Every id the graph engine will accept as a relationship endpoint.

        The engine does not build its node set from entities.json alone. It
        promotes operational records — known errors, learned patterns,
        changes, knowledge documents and health observations — into nodes so
        that APPLIES_TO, MODIFIES and similar predicates have something to
        point at.

        A validator that checks endpoints against entities.json alone reports
        false errors on correct data, which is worse than not checking: a
        validator you learn to ignore is a validator that has stopped working.
        This mirrors graph_engine.add_operational_nodes and must be updated
        with it.
        """
        return (
            self.entity_ids
            | self.ids("known_errors", "known_error_id")
            | self.ids("learned_patterns", "known_error_id")
            | self.ids("changes", "change_id")
            | self.ids("knowledge_documents", "document_id")
            | self.ids("health_observations", "observation_id")
        )

    @property
    def pattern_ids(self) -> set[str]:
        """Curated known errors plus anything the system learned."""
        return self.ids("known_errors", "known_error_id") | self.ids(
            "learned_patterns", "known_error_id"
        )

    def counts(self) -> dict[str, int]:
        return {
            name: len(rows)
            for name, rows in sorted(self.observable.items())
            if rows
        }

    def truth_counts(self) -> dict[str, int]:
        return {
            name: len(rows) for name, rows in sorted(self.truth.items()) if rows
        }
