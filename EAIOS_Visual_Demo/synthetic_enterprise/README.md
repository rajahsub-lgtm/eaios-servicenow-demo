# Synthetic enterprise — validation

Validators for the synthetic enterprise compiler. Written before the
generator, so they define the acceptance criteria rather than describe
whatever was produced.

```
python -m synthetic_enterprise.validation.runner json/
python -m synthetic_enterprise.validation.runner generated/golden-001 --json report.json
```

Exit code is 1 on any ERROR, so it can gate a build.

## Status

| Validator | State |
|---|---|
| `referential` | built, proven |
| `temporal` | built, proven |
| `causal` | not started — needs ground-truth episode schema |
| `statistical` | not started — needs the long-tail targets |
| `architecture` | not started |
| `adversarial/*` | not started |

## How these were proven

Two steps, in order, and the first matters as much as the second.

**Run against known-good data.** The hand-crafted 30-entity fixture set is
coherent by construction, so anything the validators report on it is a fault
in the validator.

This immediately caught one. The first version checked relationship endpoints
against `entities.json` and reported 19 dangling references on correct data.
`graph_engine.py` does not build its node population from `entities.json`
alone — it promotes known errors, learned patterns, changes, knowledge
documents and health observations into nodes so that `APPLIES_TO`, `MODIFIES`
and similar predicates have something to point at. The validator was checking
a different system than the one that runs.

That failure mode is worse than no validator. False errors on correct data
train you to ignore the report, and then the real error arrives and is ignored
with it.

**Then inject each fault and confirm it fires.** A guard nobody has seen fail
is not known to work.

```
outcome references a pattern that was never generated   pattern_exists          YES
duplicate outcome id                                    unique_identity         YES
relationship points at a missing node                   reference_exists        YES
document covers an entity that does not exist           document_entity_exists  YES
incident resolved before it opened                      record_ordering         YES
unparseable timestamp                                   timestamp_parses        YES
known error expires before it begins                    validity_window         YES
```

7/7.

## What the findings say

A finding names the rule, the record, and the consequence. "Referential
integrity failure" is not useful; this is:

> `[ERROR] referential·pattern_exists (outcome_history.known_error_id)`
> 1 row references 1 pattern that does not exist
> → The experience ledger counts zero cases for these, so a pattern the
>   demonstration relies on has no history behind it and nothing reports the
>   loss.

That third line is the point. Every rule states what breaks, because a
validator that reports a violation without a consequence gets argued with.

## Two worlds

`Dataset` loads observable evidence and ground truth into separate attributes
and never merges them. A validator that reaches for ground truth has to name
`dataset.truth` in its own code, which makes the reach visible in review.

| Attribute | Contents |
|---|---|
| `dataset.observable` | What the reasoning system may read |
| `dataset.truth` | Hidden causal record — generator and validators only |

## Notes for the generator

**`graph_node_ids` mirrors `graph_engine.add_operational_nodes`.** If the
engine's promotion list changes, this must change with it, or the validator
drifts back into checking a different system.

**Missing fixtures are not errors.** A generator under development produces
partial output, and a validator that crashes on an absent file cannot report
on the files that exist. Absence is reported as INFO.

**Both layouts work.** Fixtures may sit at the dataset root or under `json/`.
