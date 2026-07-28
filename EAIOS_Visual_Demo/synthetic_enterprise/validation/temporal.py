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

from .dataset import Dataset, parse_time
from .findings import Finding, error, info, warn


NAME = "temporal"

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
    return findings


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
        "knowledge_documents": ("published_at", "last_validated_at"),
    }
    for fixture, names in fields.items():
        rows = dataset[fixture]
        if not rows:
            continue
        bad = Counter()
        for row in rows:
            for name in names:
                raw = row.get(name)
                if raw not in (None, "") and parse_time(raw) is None:
                    bad[name] += 1
        for name, count in bad.items():
            findings.append(
                error(
                    NAME,
                    "timestamp_parses",
                    f"{count} unparseable {name} in {fixture}",
                    subject=f"{fixture}.{name}",
                    consequence=(
                        "The engine parses with a fixed format and raises — "
                        "one bad row fails the whole assessment at runtime."
                    ),
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
