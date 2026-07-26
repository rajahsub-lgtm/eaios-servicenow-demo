"""Re-plan every scenario against altered confidence thresholds.

The demo claims the plan is a consequence of the evidence rather than a
setting. A control that changes the setting and shows the plan following is
the only way to make that falsifiable in front of an audience.

Nothing here is simulated. A temporary config tree is written with the chosen
bands and the real orchestrator runs against it, because a slider that moved a
number without re-planning would be a claim about the architecture rather than
a demonstration of it.

This lives outside the Streamlit app so it can be tested without a browser.
The app wraps it for caching and does not hold the logic itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator


# The scenarios worth putting under the control: two that can lose their
# shortcut when the bar rises, and four that cannot gain one when it falls.
CONTROL_SCENARIOS: tuple[tuple[str, str], ...] = (
    ("SCN-PAY-001", "Payment — 49 cases"),
    ("SCN-PAY-RESOLVED-001", "Payment — contradiction resolved"),
    ("SCN-CROSS-GATEWAY-001", "GitHub + Teams — shared gateway"),
    ("SCN-PAY-EU-001", "Payment EU — by analogy"),
    ("SCN-QUEUE-001", "Order queue — weak history"),
    ("SCN-NOVEL-INDEX-001", "Search indexer — from the manual"),
)


@dataclass(frozen=True)
class ScenarioOutcome:
    scenario_id: str
    label: str
    confidence: float
    band: str
    plan: str
    agents: int
    readiness: str
    blocked_by: tuple[str, ...]


def blocking_flags(base_dir: str | Path) -> frozenset[str]:
    """Flags that bar the accelerated plan, read from policy.

    Read rather than restated so the panel cannot drift from what actually
    blocks a plan.
    """
    policies = json.loads(
        (Path(base_dir) / "config" / "orchestration_policies.json").read_text(
            encoding="utf-8"
        )
    )
    accelerated = next(
        mode
        for mode in policies["modes"]
        if mode["mode_id"] == "ACCELERATED_VALIDATION"
    )
    return frozenset(accelerated["entry_conditions"]["disallowed_hard_flags"])


def shipped_levels(base_dir: str | Path) -> dict[str, float]:
    return json.loads(
        (Path(base_dir) / "config" / "confidence_policy.json").read_text(
            encoding="utf-8"
        )
    )["levels"]


def run_at_thresholds(
    base_dir: str | Path, *, high: float, medium: float
) -> list[ScenarioOutcome]:
    """Execute every control scenario against the given confidence bands."""
    base_dir = Path(base_dir)
    barred = blocking_flags(base_dir)

    with TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copytree(base_dir / "config", root / "config")
        policy_path = root / "config" / "confidence_policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["levels"]["HIGH"] = float(high)
        policy["levels"]["MEDIUM"] = float(medium)
        policy_path.write_text(
            json.dumps(policy, indent=2), encoding="utf-8"
        )

        outcomes = []
        for scenario_id, label in CONTROL_SCENARIOS:
            # json_dir stays the real one, so only the confidence bands differ
            # from a normal run.
            result = AdaptiveExecutionOrchestrator(
                root, json_dir=base_dir / "json"
            ).execute(
                correlation_id=f"CTRL-{scenario_id}", scenario_id=scenario_id
            )
            # What is holding this scenario in the full plan, right now.
            # Derived from the plan that was actually chosen, not from the
            # accumulated uncertainty factors: those keep a permanent record
            # of everything considered, including flags later resolved at
            # runtime. The gateway scenario has its high-risk-change flag
            # retired mid-run and then accelerates, so reading the factor list
            # would caption an accelerated plan with the reason it was blocked.
            blocked: tuple[str, ...] = ()
            if result.final_plan_mode != "ACCELERATED_VALIDATION":
                blocked = tuple(
                    sorted(
                        set(result.recommendation.get("uncertainty_factors", []))
                        & barred
                    )
                )
            outcomes.append(
                ScenarioOutcome(
                    scenario_id=scenario_id,
                    label=label,
                    confidence=round(result.initial_confidence_score, 3),
                    band=result.final_confidence_level,
                    plan=result.final_plan_mode,
                    agents=result.reasoning_agent_execution_count,
                    readiness=result.automation_readiness["status"],
                    blocked_by=blocked,
                )
            )
        return outcomes


def replanned(
    baseline: list[ScenarioOutcome], current: list[ScenarioOutcome]
) -> list[tuple[ScenarioOutcome, ScenarioOutcome]]:
    """Scenarios whose plan changed, paired before and after."""
    return [
        (before, after)
        for before, after in zip(baseline, current)
        if before.plan != after.plan
    ]
