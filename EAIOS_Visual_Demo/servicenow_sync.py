from __future__ import annotations

from pathlib import Path
import argparse
import json

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from adaptive_servicenow_mapper import AdaptiveServiceNowMapper
from servicenow_repository import ServiceNowAssessmentRepository
from servicenow_table_client import ServiceNowCredentials, ServiceNowTableClient


ROOT = Path(__file__).resolve().parent


def known_scenario_ids() -> list[str]:
    """Scenarios the CLI will accept, read from the fixture rather than fixed.

    A hardcoded list silently excludes any scenario added later, which is how
    a working scenario ends up unable to reach ServiceNow at all.
    """
    rows = json.loads(
        (ROOT / "json" / "scenarios.json").read_text(encoding="utf-8")
    )
    return [row["scenario_id"] for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "scenario_id",
        choices=known_scenario_ids(),
        help="Scenario to assess. Choices are read from json/scenarios.json.",
    )
    parser.add_argument("--correlation-id", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    args = parser.parse_args()

    assessment = AdaptiveExecutionOrchestrator(ROOT).execute(
        correlation_id=args.correlation_id,
        scenario_id=args.scenario_id,
    )
    mapper = AdaptiveServiceNowMapper(
        ROOT / "config" / "servicenow_field_mapping.json"
    )
    outputs = ROOT / "outputs"
    outputs.mkdir(exist_ok=True)

    if args.dry_run:
        preview = mapper.dry_run_preview(assessment)
        path = outputs / f"servicenow_dry_run_{args.correlation_id}.json"
        path.write_text(json.dumps(preview, indent=2), encoding="utf-8")
        print(f"Dry run only; no ServiceNow write performed.\nSaved: {path}")
        return

    payload = mapper.map_for_live(assessment)
    client = ServiceNowTableClient(ServiceNowCredentials.from_env())
    repository = ServiceNowAssessmentRepository(
        client, mapper.target_table, mapper.correlation_field
    )
    result = repository.upsert(args.correlation_id, payload)
    path = outputs / f"servicenow_sync_{args.correlation_id}.json"
    path.write_text(json.dumps({
        "action": result.action,
        "table": result.table,
        "correlation_id": result.correlation_id,
        "sys_id": result.sys_id,
        "record": result.record,
    }, indent=2), encoding="utf-8")
    print(f"ServiceNow action: {result.action}")
    print(f"Record sys_id: {result.sys_id}")
    print(f"Saved: {path}")


if __name__ == "__main__":
    main()
