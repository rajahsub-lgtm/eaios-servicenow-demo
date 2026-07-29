# Generator fixes — remaining work

Consolidated from validation of v1.0 and v1.1. **Only what is still
outstanding** — the v1.0 schema work is done and is not repeated here.

Current state: graph builds (68,110 nodes), engine constructs (100 patterns,
50,000 outcomes), all references resolve, all 2,000 entities connected,
identifiers unique, no ordering violations, private truth correctly excluded.

Three blockers. Two mechanical, one a design decision.

---

## Fix 1 · Timestamp formats — two of them, per field

Every timestamp is ISO-8601 with an offset (`2024-01-01T00:20:00+00:00`). The
engine calls `strptime` with fixed formats and raises at **first assessment**,
not at load. 240,000 values across sixteen fields.

**The engine uses two formats. Emitting one everywhere fails whichever half
you did not pick.**

### `%Y-%m-%d %H:%M:%S`

```
outcome_history.recorded_at
incidents.opened_at, incidents.resolved_at
changes.implemented_at, changes.planned_start, changes.planned_end
health_observations.observed_at
telemetry_samples.observed_at
vendor_advisories.observed_at, vendor_advisories.published_at
problems.opened_at, problems.closed_at
semantic_relationships.valid_from, semantic_relationships.valid_to
```

### `%Y-%m-%d` — date only, a time component **raises**

```
known_errors.valid_from, known_errors.valid_to
learned_patterns.valid_from, learned_patterns.valid_to
```

`experience_ledger` parses a pattern's validity window date-only, so
`2026-01-01 00:00:00` fails there while being required in the list above.

### Either — sliced to ten characters before parsing

```
knowledge_documents.published_at, knowledge_documents.last_validated_at
```

---

## Fix 2 · `metric_definitions` field name

```
generator emits:  {"metric_id": "request_latency_ms", "symptoms": [...]}
engine reads:     metric.get("symptom_categories", [])
```

Rename `symptoms` → `symptom_categories`.

**Consequence if not fixed:** every case fingerprint carries no symptoms.
Symptom overlap is the highest-weighted similarity dimension at 0.26, so
nothing can score. One field name silently disables recall entirely.

---

## Fix 3 · Patterns and observations must share an entity

**The substantive one.** With fixes 1 and 2 applied in memory, all 120
scenarios assess cleanly and **all 120 return 0.000 with zero candidates.**

```
health_observations entity prefixes   {'SVC': 50000}          100% services
known_errors applies_to prefixes      COMP 21, DATA 23, VENDOR 20,
                                      INFRA 16, POL 16, CLOUD 4   — no SVC
```

Four of seven similarity dimensions are pinned at zero by construction:

| Dimension | Weight | Why zero |
|---|---|---|
| `declared_applicability` | 0.28 | 2,144 `APPLIES_TO` edges, none reaching an `SVC-*` |
| `same_entity` | 0.18 | No pattern applies to any observed entity |
| `structural_position` | 0.14 | Services depend on `INFRA-*`, components on `CLOUD-*`/`DATA-*` — nothing shared |
| `entity_kind` | 0.06 | `APPLICATION_SERVICE` vs `SOFTWARE_COMPONENT` |

```
best achievable similarity   0.318
similarity floor             0.350
cases clearing the floor     0 / 25
```

### Any one of three fixes works

1. **Raise observations on the entity the pattern applies to.** Smallest change
   and the most faithful — a fault occurs on a component, so the observation
   is of that component.
2. **Add `APPLIES_TO` edges from patterns to the services above them.** Worth
   0.28 alone; clears the floor by itself when the symptom also matches, and
   demonstrates curated expert knowledge, which the demonstration wants.
3. **Give services and their components shared structural context** — common
   `parent_services` or `depends_on` — so `structural_position` contributes.

**Do not lower the similarity floor.** 0.35 is calibrated against working
fixtures; moving it masks the topology problem and degrades recall everywhere
else.

---

## Fix 4 · The compatibility check asserts the wrong thing

`compatibility_validation.json` reports:

```json
"known_errors_recallable": true,
"scenarios_runnable": true,
"status": "PASS"
```

Neither holds. It appears to verify that patterns have an admissible
`knowledge_status` and `trust_level` — true, all 100 do — rather than that any
pattern can be **reached** by a case.

Assert an outcome, not a property:

```python
engine = OperationalConfidenceEngine(dataset, "config/confidence_policy.json")
for scenario in engine.scenarios[:50]:
    a = engine.assess(scenario["scenario_id"])
    assert a.candidate_assessments, f"{scenario['scenario_id']}: nothing recalled"
    assert a.confidence_score > 0
```

A check that passes on data which cannot run is indistinguishable from success
until something tries to use it.

---

## Not yet verifiable — blocked behind the above

These need a dataset that recalls before they can be measured:

| Target | Why it matters |
|---|---|
| Long-tail outcome distribution | With ~500 outcomes per pattern, nearly all clear `minimum_outcome_sample` (15) and the confidence spread collapses. Need many patterns with 1–5 cases and a few with hundreds |
| ≥20% transferred experience | Otherwise `TRANSFERRED` never appears and the analogy story has nothing behind it |
| ≥10% non-diagnosis or documentation-only | The governed-refusal path needs cases that reach it |
| Adversarial leakage probes | Feature audit, trivial-classifier probe, grouped splits |
| Derived-summary agreement | `known_errors.historical_success_rate_numeric` must match the generated outcomes, or the dataset contradicts itself |

---

## Verification sequence

```bash
python -m synthetic_enterprise.validation.runner <dataset>
```

Then the gate that matters — the engine must actually recall:

```python
assert engine.assess(sid).candidate_assessments
```

Expect a **spread** of confidence across bands. If every scenario returns the
same number, something upstream is uniform that should not be.

Then the 472 tests.

---

## Priority

Fixes 1 and 2 are mechanical — perhaps an hour. Fix 3 is a topology decision
and is where the thinking is. Fix 4 prevents the next round trip.

**Nothing downstream can be assessed until fix 3 lands**, because a dataset
that recalls nothing produces no confidence spread, no transferred experience,
no non-diagnosis distribution and no leakage surface to probe.
