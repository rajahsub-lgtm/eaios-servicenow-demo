"""Run the demonstration the way a panel will see it, without the UI.

Prints every beat with the numbers that will be on screen, the claim the app
will make about it, and the evidence behind it. Anything that would render
empty or read wrong is reported rather than discovered live.

Run this before a demo. It takes about a minute and it is the difference
between finding a problem here and finding it in front of people.

    python rehearse.py            full arc
    python rehearse.py --brief    numbers only
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import sys

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from case_fingerprint import CaseFingerprinter
from eaios_story_data import StoryRepository
from outcome_feedback import (
    OutcomeFeedbackStore,
    OutcomeInput,
    feedback_from_assessment,
)
from pattern_learning import PatternLearner, ValidationDecision


ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT / "outputs" / "servicenow_story_bundle.json"

BEATS = {
    "EAIOS-DEMO-STABLE-001": (
        1,
        "It has seen this 49 times",
        "Confidence is earned from recorded outcomes, and it buys a narrower plan.",
    ),
    "EAIOS-DEMO-CONTRADICTION-001": (
        2,
        "Confidence can be lost mid-run",
        "Credible contradiction is not promoted to truth. It costs confidence and widens the plan.",
    ),
    "EAIOS-DEMO-RESOLVED-001": (
        2,
        "Recovery is capped below the loss",
        "Evidence retires the alternative, the plan narrows again, and confidence does not fully return.",
    ),
    "EAIOS-DEMO-CROSS-GATEWAY-001": (
        3,
        "One cause, two platforms",
        "The shared dependency is discovered by traversal, not declared on the scenario.",
    ),
    "EAIOS-DEMO-TRANSFERRED-001": (
        4,
        "Never here, but fifty times next door",
        "Recognised as an analogy, and an analogy never buys the shortened plan.",
    ),
    "EAIOS-DEMO-UNSEEN-001": (
        5,
        "Never seen: read the manual",
        "A cause is proposed from the written procedure, named as its source, and held below any experienced level.",
    ),
    "EAIOS-DEMO-UNDOCUMENTED-001": (
        5,
        "Nothing written either",
        "No cause is proposed. Not knowing is a finding, not a failure.",
    ),
}


def rule(text: str) -> None:
    print(f"\n{'=' * 78}\n{text}\n{'=' * 78}")


def warn(problems: list[str], message: str) -> None:
    problems.append(message)
    print(f"  !! {message}")


def steady_plan_callout():
    source = (ROOT / "eaios_story_app.py").read_text(encoding="utf-8")
    start = source.index("def _steady_plan_callout")
    end = source.index("def render_adaptive_story")
    namespace: dict = {"Any": object}
    exec(source[start:end], namespace)
    return namespace["_steady_plan_callout"]


def check_bundle(brief: bool) -> list[str]:
    problems: list[str] = []
    if not BUNDLE.exists():
        problems.append(
            "No story bundle. Run: python demo_servicenow_storytelling.py"
        )
        print("  !! " + problems[-1])
        return problems

    repo = StoryRepository.load(ROOT)
    callout = steady_plan_callout()
    assessments = repo.assessments

    if [a["correlation_id"] for a in assessments] != list(BEATS):
        warn(
            problems,
            "Bundle order does not match the narrative. Regenerate the bundle.",
        )

    for assessment in assessments:
        correlation_id = assessment["correlation_id"]
        beat, headline, say = BEATS.get(correlation_id, (0, correlation_id, ""))
        identity = repo.scenario_identity(assessment["scenario_id"])
        rule(f"BEAT {beat} · {headline}")
        print(f"  on screen    : {identity['display_name']}")
        print(
            f"  confidence   : {assessment['initial_confidence_score']:.3f} "
            f"{assessment['initial_confidence_level']} -> "
            f"{assessment['final_confidence_score']:.3f} "
            f"{assessment['final_confidence_level']}"
        )
        print(
            f"  plan         : {assessment['initial_plan_mode']} -> "
            f"{assessment['final_plan_mode']} "
            f"({assessment['initial_agent_count']} -> "
            f"{assessment['final_agent_count']} agents)"
        )
        print(f"  readiness    : {assessment['automation_readiness']['status']}")

        recommendation = assessment.get("recommendation", {})
        if assessment["expanded_during_execution"] or assessment[
            "contracted_during_execution"
        ]:
            claim = "(plan moved — narrated by the transition)"
        else:
            claim = callout(assessment).split("</b>")[0].replace("<b>", "")
        print(f"  app claims   : {claim}")
        print(f"  you say      : {say}")

        if not brief:
            print(f"  hypothesis   : {recommendation.get('leading_hypothesis_id')}")
            action = str(recommendation.get("recommended_action", ""))
            print(f"  action       : {action[:150]}{'...' if len(action) > 150 else ''}")

        # The checks that matter: a claim the run contradicts, and approval
        # quietly disappearing.
        if assessment["final_confidence_level"] != "HIGH" and (
            "confidence stayed high" in claim.lower()
        ):
            warn(problems, f"{correlation_id}: claim contradicts the confidence")
        if not recommendation.get("human_approval_required", True):
            warn(problems, f"{correlation_id}: human approval is not required")
        if not recommendation.get("leading_hypothesis_id"):
            warn(problems, f"{correlation_id}: no hypothesis id to show")

    return problems


def check_learning_loop(brief: bool) -> list[str]:
    """Beat 6 runs live, so rehearse it live."""
    problems: list[str] = []
    rule("BEAT 6 · Seen once before, and it matters how that went")
    results = {}
    for worked in (True, False):
        with TemporaryDirectory() as directory:
            json_dir = Path(directory) / "json"
            shutil.copytree(ROOT / "json", json_dir)
            first = AdaptiveExecutionOrchestrator(ROOT, json_dir=json_dir).execute(
                correlation_id="REHEARSE-1", scenario_id="SCN-NOVEL-INDEX-001"
            )
            recommendation = first.recommendation
            pattern = PatternLearner(json_dir).learn(
                assessment=first,
                decision=ValidationDecision(
                    decision="CORRECTED",
                    validated_by="k.osei@example.com",
                    decided_at="2026-07-24 16:30:00",
                    corrected_cause="A stalled segment merge held the write lock.",
                    corrected_action="Clear the stalled merge before any restart.",
                ),
                fingerprint=CaseFingerprinter(json_dir).for_scenario(
                    "SCN-NOVEL-INDEX-001"
                ),
                document_id=recommendation["leading_hypothesis_id"],
                proposed_cause=recommendation["leading_hypothesis_title"],
                proposed_action=recommendation["recommended_action"],
                trigger_metric_id="MET-INDEX-LAG",
                external_service_id="SVC-SEARCH-001",
            )
            OutcomeFeedbackStore(
                json_dir / "runtime_outcome_feedback.json"
            ).append(
                feedback_from_assessment(
                    first,
                    OutcomeInput(
                        approval_decision="Approved",
                        human_modification="None",
                        action_performed="Validated remedy applied",
                        outcome="Successful" if worked else "Unsuccessful",
                        recovery_minutes=22.0 if worked else 95.0,
                        recurrence_within_24h=not worked,
                        evidence_usefulness_score=88.0 if worked else 30.0,
                        recorded_at="2026-07-25 09:00:00",
                    ),
                    outcome_id="OUT-REHEARSE-001",
                    known_error_id=pattern.known_error_id,
                )
            )
            second = AdaptiveExecutionOrchestrator(
                ROOT, json_dir=json_dir
            ).execute(
                correlation_id="REHEARSE-2", scenario_id="SCN-INDEX-RECUR-001"
            )
            results[worked] = (first, pattern, second)

    first, pattern, good = results[True]
    _, _, bad = results[False]
    print(f"  first sight  : {first.initial_confidence_score:.3f} from "
          f"{first.recommendation['leading_hypothesis_id']} (a runbook)")
    print(f"  human says   : CORRECTED -> {pattern.known_error_id} "
          f"({pattern.knowledge_status})")
    print(f"  remedy worked: {good.initial_confidence_score:.3f} recalling "
          f"{good.recommendation['leading_hypothesis_id']}")
    print(f"  remedy failed: {bad.initial_confidence_score:.3f}")
    print("  you say      : Same pattern, same presentation. What happened last "
          "time is the difference.")

    if good.initial_confidence_score <= bad.initial_confidence_score:
        warn(problems, "the two branches no longer differ — beat 6 has no point")
    if not brief:
        factors = bad.recommendation.get("uncertainty_factors", [])
        print(f"  failure flag : "
              f"{[f for f in factors if 'INEFFECTIVE' in f] or 'MISSING'}")
    if not any(
        "INEFFECTIVE" in f
        for f in bad.recommendation.get("uncertainty_factors", [])
    ):
        warn(problems, "the failed remedy is no longer named as ineffective")
    return problems


def check_environment() -> list[str]:
    problems: list[str] = []
    rule("ENVIRONMENT")
    for module in ("streamlit", "plotly.express", "pandas"):
        try:
            __import__(module)
            print(f"  ok           : {module}")
        except ImportError:
            warn(problems, f"{module} is not installed — the app will not start")
    if BUNDLE.exists():
        age = datetime.now() - datetime.fromtimestamp(BUNDLE.stat().st_mtime)
        print(f"  bundle age   : {age.days}d {age.seconds // 3600}h")
        if age > timedelta(days=7):
            warn(
                problems,
                "bundle is over a week old; regenerate so it matches the code",
            )
    return problems


def main() -> None:
    # The Windows console defaults to cp1252 and mangles every dash in this
    # output. A presenter reading garbled text minutes before a demo has no
    # way to tell cosmetic corruption from a real fault.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    brief = "--brief" in sys.argv
    problems = check_environment()
    problems += check_bundle(brief)
    problems += check_learning_loop(brief)

    rule("READY?" if not problems else "NOT READY")
    if problems:
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)
    print("  Seven beats in the bundle, beat six runs live, environment intact.")
    print("  Start the app:  python -m streamlit run eaios_story_app.py")


if __name__ == "__main__":
    main()
