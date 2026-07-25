from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json


@dataclass(frozen=True)
class RuntimeEvidenceSignal:
    signal_id: str
    signal_type: str
    entity_id: str
    discovered_after_skill: str
    source_system: str
    description: str
    data_classification: str
    provenance: str
    scenario_id: str | None = None
    knowledge_source_id: str | None = None
    evidence_disposition: str | None = None
    contradicts_known_error_id: str | None = None


class RuntimeEvidenceProbe:
    """Read newly discoverable operational evidence.

    Events are data. Adding a new event changes behavior without changing
    planner or executor code. Scenario scoping prevents one synthetic event
    from changing unrelated demonstrations that share the same entity graph.
    """

    def __init__(self, json_dir: str | Path) -> None:
        self.path = Path(json_dir) / "runtime_evidence_events.json"

    def discover(
        self,
        *,
        scenario_id: str,
        entity_ids: set[str],
        after_skill: str,
    ) -> list[RuntimeEvidenceSignal]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            rows = json.load(f)

        result = []
        for row in rows:
            configured_scenario = row.get("scenario_id")
            if configured_scenario and configured_scenario != scenario_id:
                continue
            if row.get("entity_id") not in entity_ids:
                continue
            if row.get("discovered_after_skill") != after_skill:
                continue
            result.append(RuntimeEvidenceSignal(**row))
        return result

    @staticmethod
    def to_dict(signal: RuntimeEvidenceSignal) -> dict:
        return asdict(signal)
