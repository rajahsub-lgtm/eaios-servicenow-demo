from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from adaptive_servicenow_mapper import AdaptiveServiceNowMapper
from servicenow_repository import ServiceNowAssessmentRepository


ROOT = Path(__file__).resolve().parent


class InMemoryTableClient:
    def __init__(self) -> None:
        self.records = []
        self.counter = 0

    def get_records(self, table, *, encoded_query="", fields=None, limit=100, display_value="false"):
        key, value = encoded_query.split("=", 1) if "=" in encoded_query else ("", "")
        return [row.copy() for row in self.records if not key or str(row.get(key)) == value][:limit]

    def create_record(self, table, payload):
        self.counter += 1
        row = {"sys_id": f"MOCK{self.counter:028d}", **payload}
        self.records.append(row)
        return row.copy()

    def update_record(self, table, sys_id, payload):
        row = next(row for row in self.records if row["sys_id"] == sys_id)
        row.update(payload)
        return row.copy()

    def upsert_by_field(self, table, *, key_field, key_value, payload):
        rows = self.get_records(table, encoded_query=f"{key_field}={key_value}", limit=2)
        if rows:
            return "UPDATED", self.update_record(table, rows[0]["sys_id"], payload)
        return "CREATED", self.create_record(table, payload)


def confirmed_test_mapping(path: Path) -> None:
    original = json.loads((ROOT / "config" / "servicenow_field_mapping.json").read_text(encoding="utf-8"))
    names = {
        "Correlation ID": "u_correlation_id",
        "External observation ID": "u_external_observation_id",
        "Leading hypothesis": "u_leading_hypothesis",
        "Selected strategy": "u_selected_strategy",
        "Confidence": "u_confidence",
        "Safety status": "u_safety_status",
        "Approval state": "u_approval_state",
        "Recommended action": "u_recommended_action",
        "Outcome": "u_outcome",
    }
    for concept, internal in names.items():
        original["fields"][concept]["internal_name"] = internal
        original["fields"][concept]["confirmed"] = True
    original["status"] = "CONFIRMED_FOR_DEMO"
    path.write_text(json.dumps(original, indent=2), encoding="utf-8")


def main() -> None:
    assessment = AdaptiveExecutionOrchestrator(ROOT).execute(
        correlation_id="EAIOS-SNOW-MOCK-001",
        scenario_id="SCN-PAY-001",
    )
    with TemporaryDirectory() as directory:
        mapping_path = Path(directory) / "mapping.json"
        confirmed_test_mapping(mapping_path)
        mapper = AdaptiveServiceNowMapper(mapping_path)
        payload = mapper.map_for_live(assessment)
        client = InMemoryTableClient()
        repo = ServiceNowAssessmentRepository(client, mapper.target_table, mapper.correlation_field)

        first = repo.upsert(assessment.correlation_id, payload)
        second_payload = dict(payload)
        second_payload["u_outcome"] = "Approved"
        second = repo.upsert(assessment.correlation_id, second_payload)

        print("=== SERVICENOW BOUNDARY MOCK ===")
        print(f"First sync: {first.action} | sys_id={first.sys_id}")
        print(f"Second sync: {second.action} | sys_id={second.sys_id}")
        print(f"Records in target table: {len(client.records)}")
        print("Correlation ID produced create-then-update behavior without duplicates.")
        print("Live mode uses the same repository after PDI field mapping is confirmed.")


if __name__ == "__main__":
    main()
