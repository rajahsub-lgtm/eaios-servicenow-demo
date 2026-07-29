"""Does the dataset respect the order in which things can happen?

Causal ordering is the invariant most easily broken by a generator that fills
timestamps independently, and it is the one an audience notices: a
recommendation approved before it was made, or a post-incident review that
informed the incident it reviews.

The document-availability rule is the sharpest of these, because the reasoning
system already enforces it. A document published after an assessment cannot
have informed it, and a generator that ignores this produces a demonstration
whose own engine will refuse the evidence.
"""

from __future__ import annotations

from collections import Counter

from datetime import datetime

from .dataset import Dataset, parse_time
from .findings import Finding, error, info, warn


NAME = "temporal"

# The exact format operational_confidence_engine.DATETIME_FORMAT demands.
# The engine calls strptime with this and nothing else; anything it cannot
# parse raises at assessment time rather than at load.
#
# The validator must check THIS, not whether a human would call the value a
# timestamp. An earlier version used the tolerant parser below and passed a
# dataset in which every single timestamp was ISO-8601 with an offset — 240,000
# values the engine could not read. A validator more permissive than the
# system it guards reports success on data that cannot run.
ENGINE_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
ENGINE_DATE_FORMAT = "%Y-%m-%d"

# The engine does not use one format. It uses two, and which applies is
# per-field — taken from the strptime call sites and confirmed against the
# shipped fixtures, which are the working ground truth.
#
# The distinction is not cosmetic. experience_ledger parses a pattern's
# validity window with the date-only format, so "2026-01-01 00:00:00" raises
# there while being required elsewhere. A generator emitting one format
# everywhere fails whichever half it did not choose.
DATE_ONLY_FIELDS = {
    ("known_errors", "valid_from"),
    ("known_errors", "valid_to"),
    ("learned_patterns", "valid_from"),
    ("learned_patterns", "valid_to"),
}

# Sliced to ten characters before parsing, so either form is accepted.
TOLERANT_FIELDS = {
    ("knowledge_documents", "published_at"),
    ("knowledge_documents", "last_validated_at"),
}


def required_format(fixture: str, field_name: str) -> str | None:
    """The format the engine will use for this field, or None if tolerant."""
    if (fixture, field_name) in TOLERANT_FIELDS:
        return None
    if (fixture, field_name) in DATE_ONLY_FIELDS:
        return ENGINE_DATE_FORMAT
    return ENGINE_DATETIME_FORMAT


def engine_parseable(value, fmt: str | None) -> bool:
    if value in (None, "") or fmt is None:
        return True
    try:
        datetime.strptime(str(value), fmt)
        return True
    except (ValueError, TypeError):
        return False

# Orderings that must hold inside a single record.
WITHIN_RECORD = (
    ("incidents", "opened_at", "resolved_at", "an incident resolved before it opened"),
    ("changes", "planned_start", "planned_end", "a change that ended before it started"),
    ("problems", "opened_at", "closed_at", "a problem closed before it opened"),
    (
        "knowledge_documents",
        "published_at",
        "last_validated_at",
        "a document validated before it was published",
    ),
)


def validate(dataset: Dataset) -> list[Finding]:
    findings: list[Finding] = []
    findings += _parseable(dataset)
    findings += _within_record(dataset)
    findings += _validity_windows(dataset)
    findings += _episode_ordering(dataset)
    findings += _document_availability(dataset)
    findings += _history_precedes_assessment(dataset)
    return findings


def _history_precedes_assessment(dataset: Dataset) -> list[Finding]:
    """Is there any experience behind the cases being assessed?

    The engine counts only outcomes recorded on or before the assessment
    moment, which is correct — a case cannot learn from its own future. A
    generator that places its scenarios at the start of the timeline therefore
    produces a dataset where every pattern recalls with zero history, scores
    zero, and demonstrates nothing, while appearing to contain fifty thousand
    outcomes.

    Nothing else catches this. Referential integrity passes, every timestamp
    parses, causal ordering inside each episode holds. The fault is only
    visible when history and assessment time are compared across the corpus.
    """
    scenarios = dataset["scenarios"]
    outcomes = dataset["outcome_history"]
    observations = {
        row.get("observation_id"): row for row in dataset["health_observations"]
    }
    if not scenarios or not outcomes or not observations:
        return []

    recorded = sorted(
        t for t in (parse_time(r.get("recorded_at")) for r in outcomes) if t
    )
    if not recorded:
        return []

    starved, total = 0, 0
    coverage: list[float] = []
    for scenario in scenarios:
        observation = observations.get(scenario.get("trigger_observation_id"))
        assessed = parse_time(observation.get("observed_at")) if observation else None
        if not assessed:
            continue
        total += 1
        # recorded is sorted, so a bisect would be faster; the corpus is small
        # enough here that clarity wins.
        before = sum(1 for t in recorded if t <= assessed)
        coverage.append(before / len(recorded))
        if before == 0:
            starved += 1

    if not total:
        return []

    median = sorted(coverage)[len(coverage) // 2]
    if starved or median < 0.10:
        return [
            error(
                NAME,
                "history_precedes_assessment",
                f"{starved} of {total} scenarios have no recorded outcome "
                f"before them; the median scenario has {median:.1%} of the "
                f"corpus behind it",
                consequence=(
                    "The engine counts only outcomes recorded on or before "
                    "the assessment. Scenarios placed at the start of the "
                    "timeline recall a pattern, find no history, and score "
                    "zero — so the dataset appears to hold the experience it "
                    "is meant to demonstrate while none of it is reachable. "
                    "Draw scenarios from the END of the generated period."
                ),
                detail={
                    "scenarios_with_no_history": starved,
                    "median_corpus_share_available": round(median, 4),
                },
            )
        ]

    return [
        info(
            NAME,
            "history_precedes_assessment",
            f"median scenario has {median:.1%} of the outcome corpus behind it",
        )
    ]


def _parseable(dataset: Dataset) -> list[Finding]:
    """A timestamp that will not parse is worse than one that is wrong.

    The confidence engine parses with a fixed format and raises. One bad row
    in fifty thousand takes the whole assessment down at runtime.
    """
    findings = []
    fields = {
        "outcome_history": ("recorded_at",),
        "incidents": ("opened_at", "resolved_at"),
        "changes": ("implemented_at", "planned_start", "planned_end"),
        "health_observations": ("observed_at",),
        "telemetry_samples": ("observed_at",),
        "vendor_advisories": ("observed_at", "published_at"),
        "problems": ("opened_at", "closed_at"),
        "known_errors": ("valid_from", "valid_to"),
        "learned_patterns": ("valid_from", "valid_to"),
        "knowledge_documents": ("published_at", "last_validated_at"),
    }
    for fixture, names in fields.items():
        rows = dataset[fixture]
        if not rows:
            continue
        bad = Counter()
        examples: dict[str, str] = {}
        for row in rows:
            for name in names:
                raw = row.get(name)
                if raw in (None, ""):
                    continue
                if not engine_parseable(raw, required_format(fixture, name)):
                    bad[name] += 1
                    examples.setdefault(name, str(raw))
        for name, count in bad.items():
            total = sum(1 for r in rows if r.get(name))
            readable = parse_time(examples[name]) is not None
            findings.append(
                error(
                    NAME,
                    "timestamp_parses",
                    f"{count} of {total} {name} in {fixture} are not in the "
                    f"format the engine requires",
                    subject=f"{fixture}.{name}",
                    consequence=(
                        "The engine calls strptime with "
                        f"'{required_format(fixture, name)}' and raises on "
                        "anything else. This is a runtime failure at "
                        "assessment, not a "
                        "load failure — the data imports cleanly and then the "
                        "first assessment dies."
                    )
                    + (
                        " The value is a valid timestamp in another format, so "
                        "this is a serialisation choice rather than corrupt "
                        "data."
                        if readable
                        else ""
                    ),
                    detail={
                        "example": examples[name],
                        "required": required_format(fixture, name),
                    },
                )
            )
    return findings


def _within_record(dataset: Dataset) -> list[Finding]:
    findings = []
    for fixture, first, second, description in WITHIN_RECORD:
        rows = dataset[fixture]
        if not rows:
            continue
        offenders = []
        for row in rows:
            start, end = parse_time(row.get(first)), parse_time(row.get(second))
            if start and end and end < start:
                offenders.append(row.get(f"{fixture[:-1]}_id") or row.get("document_id"))
        if offenders:
            findings.append(
                error(
                    NAME,
                    "record_ordering",
                    f"{len(offenders)} rows in {fixture}: {description}",
                    subject=f"{fixture}.{first}→{second}",
                    detail={"examples": [o for o in offenders[:5] if o]},
                )
            )
    return findings


def _validity_windows(dataset: Dataset) -> list[Finding]:
    findings = []
    for fixture in ("known_errors", "semantic_relationships", "learned_patterns"):
        rows = dataset[fixture]
        if not rows:
            continue
        inverted = 0
        for row in rows:
            start = parse_time(row.get("valid_from"))
            end = parse_time(row.get("valid_to"))
            if start and end and end < start:
                inverted += 1
        if inverted:
            findings.append(
                error(
                    NAME,
                    "validity_window",
                    f"{inverted} rows in {fixture} expire before they begin",
                    subject=fixture,
                    consequence=(
                        "Admissibility filters on this window, so these are "
                        "permanently invisible to recall."
                    ),
                )
            )
    return findings


def _episode_ordering(dataset: Dataset) -> list[Finding]:
    """Change → symptom → incident → decision → action → recovery.

    Checked against ground truth where the generator provides it, and against
    what can be inferred from observables where it does not.
    """
    findings = []
    episodes = dataset.truth.get("ground_truth_episodes", [])

    if not episodes:
        findings.append(
            info(
                NAME,
                "episode_truth_absent",
                "no ground_truth_episodes present — causal ordering can only "
                "be checked from observables",
                consequence=(
                    "Full episode ordering needs the hidden timeline. Without "
                    "it, a recommendation approved before it was proposed "
                    "cannot be detected."
                ),
            )
        )
        return findings

    sequence = (
        "change_implemented_at",
        "fault_active_at",
        "first_symptom_at",
        "threshold_breached_at",
        "incident_opened_at",
        "recommendation_at",
        "approval_at",
        "action_at",
        "recovery_at",
        "resolution_validated_at",
    )

    broken = Counter()
    for episode in episodes:
        stamps = [(name, parse_time(episode.get(name))) for name in sequence]
        present = [(n, t) for n, t in stamps if t]
        for (earlier_name, earlier), (later_name, later) in zip(
            present, present[1:]
        ):
            if later < earlier:
                broken[f"{earlier_name} → {later_name}"] += 1

    for transition, count in broken.items():
        findings.append(
            error(
                NAME,
                "causal_ordering",
                f"{count} episodes violate {transition}",
                subject=transition,
                consequence=(
                    "The episode timeline runs backwards, so any narrative "
                    "built from it contradicts itself."
                ),
            )
        )

    if not broken:
        findings.append(
            info(
                NAME,
                "causal_ordering",
                f"{len(episodes)} episodes hold the full causal ordering",
            )
        )
    return findings


def _document_availability(dataset: Dataset) -> list[Finding]:
    """A document cannot inform a decision taken before it was written.

    The documentation reasoner already enforces publication on or before the
    assessment time, so a generator that ignores this produces evidence its
    own engine will refuse — the demonstration looks broken rather than
    governed.
    """
    findings = []
    documents = dataset["knowledge_documents"]
    incidents = dataset["incidents"]
    if not documents or not incidents:
        return findings

    published = {
        row["document_id"]: parse_time(row.get("published_at"))
        for row in documents
        if row.get("document_id")
    }

    # A post-incident review must follow the incident it reviews.
    late = 0
    for row in documents:
        if str(row.get("document_type", "")).upper() != "PIR":
            continue
        stamp = published.get(row.get("document_id"))
        if not stamp:
            continue
        referenced = str(row.get("incident_id") or row.get("source_incident") or "")
        if not referenced:
            continue
        match = next(
            (i for i in incidents if str(i.get("incident_id")) == referenced), None
        )
        opened = parse_time(match.get("opened_at")) if match else None
        if opened and stamp < opened:
            late += 1

    if late:
        findings.append(
            error(
                NAME,
                "review_follows_incident",
                f"{late} post-incident reviews published before their incident",
                consequence=(
                    "A review that predates its incident is available to the "
                    "assessment that should not have had it."
                ),
            )
        )

    undated = sum(1 for row in documents if not published.get(row.get("document_id")))
    if undated:
        findings.append(
            warn(
                NAME,
                "publication_dated",
                f"{undated} documents have no usable published_at",
                consequence=(
                    "Documents without a publication date cannot be excluded "
                    "from earlier assessments, so temporal integrity is "
                    "unenforceable for them."
                ),
            )
        )
    return findings
