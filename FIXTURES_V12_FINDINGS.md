# Fixtures v1.2 — validation findings

**The three v1.1 blockers are fixed.** Timestamps carry the correct per-field
formats, `metric_definitions` exposes `symptom_categories`, and patterns now
apply to services as well as components.

**Recall works.** This is the first version where the engine reaches a
pattern:

```
14 of 15 scenarios recalled     DIRECT 7 · TRANSFERRED 7 · NONE 1
```

Two blockers remain. The second is the substantive one and has a one-line
conceptual fix.

---

## Blocker A · Two fields are lists where the engine wants delimited strings

```
AttributeError: 'list' object has no attribute 'split'
    operational_confidence_engine.py:942
```

| Field | Engine wants | v1.2 emits |
|---|---|---|
| `knowledge_documents.entity_ids` | `"APP-0051,SVC-0051"` | `["APP-0051", "SVC-0051"]` |
| `knowledge_documents.symptom_categories` | `"PAYMENT_TIMEOUT,CONNECTOR_SATURATION"` | `["workflow completion failure"]` |

Those are the only two type mismatches across every shared field — verified by
diffing against the working fixtures rather than found one crash at a time.

### The trap worth knowing

**`symptom_categories` has two different types depending on the fixture:**

| Location | Type |
|---|---|
| `metric_definitions.symptom_categories` | **list** — `["PAYMENT_TIMEOUT"]` |
| `knowledge_documents.symptom_categories` | **delimited string** |

Same field name, same meaning, different representation, because two engine
code paths read them differently. `documented_reasoning` tolerates either;
`operational_confidence_engine._governed_knowledge` calls `.split(",")`
directly.

This is an engine wart rather than a generator error. Matching the shipped
fixtures is the safe move — 472 tests encode them — but making the engine
tolerant in both places would be a small, genuine robustness improvement and
would remove this whole class of problem. Worth doing after the demo rather
than during it.

---

## Blocker B · The scenarios sit at the beginning of history

**This is the one that matters.** With Blocker A fixed in memory, all
scenarios assess, patterns are recalled, and **every confidence score is
0.000**.

The recalled pattern's outcome profile:

```
n = 0    success 0.0    reliability 0.0    drift ERODING
penalties: recent_failure_signal_HIGH 0.15, insufficient_outcome_sample 0.08,
           eroding_confidence 0.10, missing_governed_knowledge 0.10
           sum 0.430  →  score 0.000
```

Not because the outcomes are missing. Because they have not happened yet:

```
scenario observation times    2024-01-01 00:20  ..  2024-01-10 10:43
outcome recorded_at times     2024-01-01 02:24  ..  2025-08-13 12:53

earliest scenario     0 of 50,000 outcomes before it
median scenario     394 of 50,000   (0.8%)
latest scenario     796 of 50,000   (1.6%)
```

All 800 scenarios fall in the first ten days. The 50,000 outcomes run for the
following nineteen months. **98.4% of the generated experience was recorded
after every case being assessed.**

The engine counts only outcomes recorded on or before the assessment moment,
which is correct — a case cannot learn from its own future. So every pattern
recalls, finds nothing behind it, and scores zero.

### The fix

**Draw scenarios from the end of the generated period, not the start.**

The enterprise history should sit *behind* the cases being assessed. If the
corpus spans 2024-01 to 2025-08, the scenarios belong in the final weeks, with
nineteen months of experience preceding them.

That single change should produce the confidence spread everything else is
waiting on — mature patterns scoring high, thin ones scoring low, and the
maturity ladder becoming visible.

### Why nothing else caught it

Referential integrity passes. Every timestamp parses. Causal ordering *within*
each episode holds — the change precedes the fault, the fault precedes the
symptom. The fault is only visible when history and assessment time are
compared **across** the corpus, which no per-record check does.

A validator for exactly this is now in place and fails on v1.2.

---

## Secondary · `MISSING_GOVERNED_KNOWLEDGE` on every assessment

`knowledge_readiness` scores 0.0 and the flag raises on every case. Worth
checking after Blocker B, since it costs 0.10 of confidence and bars the
narrow plan. Likely the same entity-matching question as the patterns: the
documents must name the entity being assessed in `entity_ids`, and must be
published on or before the assessment — which the timeline inversion also
breaks.

Expect this to partly resolve itself once scenarios move to the end.

---

## Performance · worth knowing before the demo

```
engine construction        3.7 s
assessment                 1.64 s each
```

At 50,000 outcomes and 100 patterns, each assessment profiles the full history
per candidate. Acceptable for a walkthrough, uncomfortable for a live slider
that re-runs six scenarios — the confidence-controls panel would take ten
seconds per drag.

Not worth optimising yet. If it becomes a problem, the outcome profile is the
hot path and is cacheable per `(pattern, assessed_at)`.

---

## What is now right

- Timestamps: correct per-field, both formats
- `metric_definitions.symptom_categories` present
- Patterns apply to services — 20 of 100 — so recall reaches observations
- Observations spread across `SVC`, `COMP`, `INFRA`, `DATA`, `VENDOR`, `CLOUD`, `POL`, `APP`
- **Recall demonstrably works**, with both `DIRECT` and `TRANSFERRED` classes appearing
- All references resolve, identifiers unique, no ordering violations

---

## Verification sequence

```bash
python -m synthetic_enterprise.validation.runner <dataset>
```

Then the gate — and now it should be about the *spread*, not just the count:

```python
scores = [engine.assess(s["scenario_id"]).confidence_score
          for s in engine.scenarios[:50]]
assert max(scores) > 0.5, "no scenario reaches usable confidence"
assert len(set(round(s, 1) for s in scores)) > 3, "no spread — something is uniform"
```

Then the 472 tests.

---

## Validator changes this round

Added `temporal·history_precedes_assessment`, which compares outcome recording
times against scenario assessment times across the corpus and fails when
scenarios have no history behind them.

This is the fourth time a check has had to be made stricter because it was
more permissive than the engine — the earlier three were tolerant timestamp
parsing, relationship endpoints checked against the wrong node population, and
type-tolerant list handling that let Blocker A through. The pattern is
consistent enough to be worth stating: **a validator that accepts what a
reasonable person would accept, rather than what the engine accepts, reports
success on data that cannot run.**
