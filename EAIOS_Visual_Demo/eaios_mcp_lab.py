import os
import json
from datetime import datetime
from pathlib import Path

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("EAIOS Diagnostics Lab")
LAB_ROLE = os.environ.get("EAIOS_LAB_ROLE", "unauthorized")
DATA = Path(__file__).parent / "json" / "telemetry_samples.json"


@mcp.tool()
def get_component_health(
    component_id: str,
    as_of: str = "2026-07-14 14:50:00",
) -> dict:
    """Read synthetic payment telemetry up to an incident timestamp.
    Missing telemetry means unknown health, not healthy.
    Returns evidence only; does not establish root cause or permit actions.
    """
    if LAB_ROLE not in {"investigator", "L1", "L2"}:
        raise PermissionError("Role is not permitted to read diagnostic evidence.")

    cutoff = datetime.strptime(as_of, "%Y-%m-%d %H:%M:%S")
    samples = json.loads(DATA.read_text(encoding="utf-8"))

    matching = [
        s for s in samples
        if s["scenario_id"] == "SCN-PAY-001"
        and s["entity_id"] == component_id
        and datetime.strptime(
            s["observed_at"], "%Y-%m-%d %H:%M:%S"
        ) <= cutoff
    ]

    latest = {}
    for sample in sorted(matching, key=lambda s: s["observed_at"]):
        latest[sample["metric_id"]] = sample

    return {
        "component_id": component_id,
        "scenario_id": "SCN-PAY-001",
        "as_of": as_of,
        "data_classification": "SYNTHETIC",
        "availability": "AVAILABLE" if matching else "UNKNOWN",
        "matching_sample_count": len(matching),
        "latest_readings": list(latest.values()),
        "limitation": "Historical simulation; not live health or proof of cause.",
    }

# Synthetic approval fixture, held by the server for this exercise.
LAB_APPROVALS = {
    "LAB-APPROVAL-001": {
        "action": "restart_database",
        "component_id": "COMP-ORDER-DB",
    }
}


@mcp.tool()
def simulate_database_restart(approval_id: str = "") -> dict:
    """Simulate a restart of the lab Order Database. No real action occurs."""
    if LAB_ROLE != "L2":
        return {
            "decision": "DENIED",
            "reason": "L2 role required.",
            "simulated_role": LAB_ROLE,
        }

    approval = LAB_APPROVALS.get(approval_id)
    if approval != {
        "action": "restart_database",
        "component_id": "COMP-ORDER-DB",
    }:
        return {
            "decision": "BLOCKED",
            "reason": "Recognized approval for this action and target required.",
            "simulated_role": LAB_ROLE,
        }

    return {
        "decision": "SIMULATED_SUCCESS",
        "component_id": "COMP-ORDER-DB",
        "approval_id": approval_id,
        "simulated_role": LAB_ROLE,
        "real_action_executed": False,
    }
