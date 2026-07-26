"""From never seen, to validated, to seen before.

Runs the same presentation three times against a scratch copy of the fixtures,
with a human validation and a recorded outcome in between, and prints what
changed. Nothing is stubbed: each encounter is a full governed run, and the
only thing that differs is what the system has recorded by the time it starts.

Two second encounters are shown, because the interesting question is not
whether confidence moves but which way. The same validated pattern, met again
after the remedy worked and after it did not, must not produce the same plan.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from case_fingerprint import CaseFingerprinter
from outcome_feedback import (
    OutcomeFeedbackStore,
    OutcomeInput,
    feedback_from_assessment,
)
from pattern_learning import PatternLearner, ValidationDecision


ROOT = Path(__file__).resolve().parent
FIRST = "SCN-NOVEL-INDEX-001"
RECURRENCE = "SCN-INDEX-RECUR-001"


def rule(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def show(assessment) -> None:
    recommendation = assessment.recommendation
    print(f"  confidence   : {assessment.initial_confidence_score:.3f} "
          f"({assessment.final_confidence_level})")
    print(f"  plan         : {assessment.final_plan_mode} "
          f"({assessment.reasoning_agent_execution_count} agents)")
    print(f"  hypothesis   : {recommendation['leading_hypothesis_id']}")
    print(f"  approval     : "
          f"{'required' if recommendation['human_approval_required'] else 'not required'}")
    readiness = assessment.automation_readiness
    print(f"  automation   : {readiness['status']}")
    print(f"  action       : {recommendation['recommended_action'][:300]}")


def run(json_dir: Path, correlation_id: str, scenario_id: str = FIRST):
    return AdaptiveExecutionOrchestrator(ROOT, json_dir=json_dir).execute(
        correlation_id=correlation_id, scenario_id=scenario_id
    )


def record_outcome(
    json_dir: Path, assessment, *, worked: bool, index: int, pattern_id: str
) -> None:
    """Write what happened when the validated remedy was applied."""
    store = OutcomeFeedbackStore(json_dir / "runtime_outcome_feedback.json")
    outcome = OutcomeInput(
        approval_decision="Approved",
        human_modification="None",
        action_performed=(
            "Stuck segment merge cleared and commit interval realigned"
            if worked
            else "Indexer restarted; lag returned within the hour"
        ),
        outcome="Successful" if worked else "Unsuccessful",
        recovery_minutes=22.0 if worked else 95.0,
        recurrence_within_24h=not worked,
        evidence_usefulness_score=88.0 if worked else 30.0,
        recorded_at=(
            datetime(2026, 7, 25) + timedelta(days=index)
        ).strftime("%Y-%m-%d 09:00:00"),
    )
    store.append(
        feedback_from_assessment(
            assessment,
            outcome,
            outcome_id=f"OUT-LEARNED-{index:03d}",
            # Against the learned pattern, not the document that proposed it.
            known_error_id=pattern_id,
        )
    )


def validate(json_dir: Path, assessment, decision: ValidationDecision):
    learner = PatternLearner(json_dir)
    fingerprint = CaseFingerprinter(json_dir).for_scenario(FIRST)
    recommendation = assessment.recommendation
    return learner.learn(
        assessment=assessment,
        decision=decision,
        fingerprint=fingerprint,
        document_id=recommendation["leading_hypothesis_id"],
        proposed_cause=recommendation["leading_hypothesis_title"],
        proposed_action=recommendation["recommended_action"],
        trigger_metric_id="MET-INDEX-LAG",
        external_service_id="SVC-SEARCH-001",
    )


def arc(label: str, *, remedy_worked: bool) -> None:
    with TemporaryDirectory() as directory:
        json_dir = Path(directory) / "json"
        shutil.copytree(ROOT / "json", json_dir)

        rule(f"{label} — ENCOUNTER 1: never seen")
        first = run(json_dir, "LEARN-1")
        show(first)

        rule("HUMAN VALIDATION")
        pattern = validate(
            json_dir,
            first,
            ValidationDecision(
                decision="CORRECTED",
                validated_by="k.osei@example.com",
                decided_at="2026-07-24 16:30:00",
                corrected_cause=(
                    "A stalled segment merge held the write lock; the commit "
                    "interval was not the cause."
                ),
                corrected_action=(
                    "Clear the stalled segment merge, then realign the commit "
                    "interval with ingest volume. Do not restart the indexer "
                    "first: it clears the lock and hides the cause."
                ),
            ),
        )
        print(f"  decision     : CORRECTED by k.osei@example.com")
        print(f"  learned      : {pattern.known_error_id}")
        print(f"  status       : {pattern.knowledge_status} "
              f"(trust {pattern.trust_level}, {pattern.historical_occurrences} case)")
        print(f"  from         : {pattern.learned_from_document_id}")
        print(f"  cause        : {pattern.probable_cause}")

        record_outcome(
            json_dir,
            first,
            worked=remedy_worked,
            index=1,
            pattern_id=pattern.known_error_id,
        )
        print(f"  outcome      : remedy "
              f"{'worked' if remedy_worked else 'did not work'}")

        rule(f"{label} — ENCOUNTER 2: seen once before")
        second = run(json_dir, "LEARN-2", RECURRENCE)
        show(second)

        print("\n  what changed:")
        print(f"    confidence {first.initial_confidence_score:.3f} -> "
              f"{second.initial_confidence_score:.3f}")
        print(f"    hypothesis {first.recommendation['leading_hypothesis_id']} -> "
              f"{second.recommendation['leading_hypothesis_id']}")


def rejection_arc() -> None:
    """A human rejects the proposal. It must not vanish."""
    with TemporaryDirectory() as directory:
        json_dir = Path(directory) / "json"
        shutil.copytree(ROOT / "json", json_dir)

        rule("REJECTION — ENCOUNTER 1")
        first = run(json_dir, "REJECT-1")
        show(first)

        refutation = validate(
            json_dir,
            first,
            ValidationDecision(
                decision="REJECTED",
                validated_by="m.varga@example.com",
                decided_at="2026-07-24 17:05:00",
                reason="Index lag tracked a storage failover, not the indexer.",
            ),
        )
        rule("HUMAN REJECTS THE PROPOSED CAUSE")
        print(f"  rejected by  : {refutation.rejected_by}")
        print(f"  reason       : {refutation.reason}")
        print(f"  recorded as  : {refutation.refutation_id}")

        rule("REJECTION — ENCOUNTER 2: same presentation, nothing better known")
        second = run(json_dir, "REJECT-2", RECURRENCE)
        show(second)
        print("\n  the account was not banned. It is ranked lower, still")
        print("  offered because nothing else explains the presentation, and")
        print("  the prior rejection is disclosed to whoever reviews it next.")


def maturity_ladder() -> None:
    """From one validated case to an established pattern.

    One case is thin evidence and scores like thin evidence, which is why the
    first recurrence sits below the documented proposal it replaced: borrowed
    authority has been traded for the system's own, and its own is nearly
    empty. What matters is the direction as cases accumulate.
    """
    rule("MATURITY — the same pattern as successful cases accumulate")
    print(f"  {'cases':>6}  {'confidence':>11}  {'plan':<22} flags")
    for cases in (1, 3, 5, 8, 12):
        with TemporaryDirectory() as directory:
            json_dir = Path(directory) / "json"
            shutil.copytree(ROOT / "json", json_dir)
            first = run(json_dir, "MATURE-0")
            pattern = validate(
                json_dir,
                first,
                ValidationDecision(
                    decision="CONFIRMED",
                    validated_by="k.osei@example.com",
                    decided_at="2026-07-24 16:30:00",
                ),
            )
            for index in range(cases):
                record_outcome(
                    json_dir,
                    first,
                    worked=True,
                    index=index + 1,
                    pattern_id=pattern.known_error_id,
                )
            later = run(json_dir, f"MATURE-{cases}", RECURRENCE)
            flags = ", ".join(later.recommendation["uncertainty_factors"][:2])
            print(f"  {cases:>6}  {later.initial_confidence_score:>11.3f}  "
                  f"{later.final_plan_mode:<22} {flags}")


def main() -> None:
    arc("REMEDY WORKED", remedy_worked=True)
    arc("REMEDY FAILED", remedy_worked=False)
    rejection_arc()
    maturity_ladder()


if __name__ == "__main__":
    main()
