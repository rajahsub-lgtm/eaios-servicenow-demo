from pathlib import Path
import argparse
import json

from adaptive_planner import AdaptivePlanner
from operational_confidence_engine import OperationalConfidenceEngine
from skill_resolver import SkillResolver


ROOT = Path(__file__).resolve().parent


def build_planner(json_dir: Path | None = None) -> AdaptivePlanner:
    json_dir = json_dir or ROOT / "json"
    confidence_engine = OperationalConfidenceEngine(
        json_dir,
        ROOT / "config" / "confidence_policy.json",
    )
    resolver = SkillResolver(
        ROOT / "config" / "skill_catalog.json",
        ROOT / "config" / "agent_registry.json",
    )
    return AdaptivePlanner(
        confidence_engine,
        resolver,
        ROOT / "config" / "orchestration_policies.json",
    )


def print_plan(plan):
    print(f"\n=== ADAPTIVE PLAN: {plan.scenario_id} ===")
    print(f"Scenario: {plan.scenario_name}")
    print(
        f"Operational confidence: {plan.confidence_level} "
        f"({plan.confidence_score:.3f})"
    )
    print(
        f"Trend: {plan.confidence_trend} | Drift: {plan.drift_status} | "
        f"Known error: {plan.selected_known_error_id}"
    )
    print(f"Mode: {plan.orchestration_mode}")
    print(f"Plan: {plan.plan_name}")
    print(f"Reasoning agents selected: {plan.reasoning_agent_count}")
    print(f"Reassessment required: {plan.reassessment_required}")
    print(f"Expansion mode: {plan.expansion_mode}")

    print("\n--- Required skills ---")
    for skill in plan.required_skills:
        print(f"- {skill}")

    print("\n--- Selected agents ---")
    for agent in plan.selected_agents:
        print(
            f"{agent.agent_id:34} | "
            f"skills={agent.assigned_skills} | "
            f"reliability={agent.reliability_score:.2f}"
        )

    print("\n--- Decision reasons ---")
    for reason in plan.decision_reasons:
        print(f"- {reason}")
    if plan.hard_flags:
        print("\n--- Hard flags ---")
        for flag in plan.hard_flags:
            print(f"- {flag}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "scenario_id",
        nargs="?",
        default="SCN-PAY-001",
        choices=["SCN-PAY-001", "SCN-QUEUE-001"],
    )
    args = parser.parse_args()

    planner = build_planner()
    plan = planner.plan(args.scenario_id)
    print_plan(plan)

    output = ROOT / "outputs" / f"adaptive_plan_{args.scenario_id}.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(
        json.dumps(planner.to_dict(plan), indent=2),
        encoding="utf-8",
    )
    print(f"\nSaved structured plan to: {output}")


if __name__ == "__main__":
    main()
