# Fixtures v1.1 — validation findings

`EAIOS_Enterprise_Engine_Fixtures_v1.1.zip` · 2,000 entities · 15,000 edges ·
50,000 outcomes · 800 scenarios · 20,000 chunks

**Progress:** the schema work landed. The graph builds (68,110 nodes), the
engine constructs (100 patterns, 50,000 outcomes), all references resolve, and
every entity is connected. The Tier 1 and Tier 2 field work from the previous
review is done.

**Status: not yet runnable.** Three blockers, found in order. The third is the
substantive one.

---

## Blocker 1 · Timestamp format — FIXED IN TEST, needs generator change

Every timestamp is ISO-8601 with an offset. The engine calls `strptime` with a
fixed format and raises.

```
ValueError: time data '2024-01-01T00:20:00+00:00'
            does not match format '%Y-%m-%d %H:%M:%S'
```

240,000 values across sixteen fields. Nothing loads-fails; the **first
assessment** dies.

### The engine uses two formats, per field

This is the part worth care — emitting one format everywhere fails whichever
half you did not pick.

| Fields | Required |
|---|---|
| `outcome_history.recorded_at`, `incidents.opened_at` / `resolved_at`, `changes.implemented_at` / `planned_start` / `planned_end`, `health_observations.observed_at`, `telemetry_samples.observed_at`, `vendor_advisories.observed_at` / `published_at`, `problems.opened_at` / `closed_at`, `semantic_relationships.valid_from` / `valid_to` | `%Y-%m-%d %H:%M:%S` |
| **`known_errors.valid_from` / `valid_to`**, `learned_patterns.valid_from` / `valid_to` | **`%Y-%m-%d`** — a time component **raises** |
| `knowledge_documents.published_at` / `last_validated_at` | either — sliced to 10 chars before parsing |

`experience_ledger` parses a pattern's validity window with the date-only
format, so `2026-01-01 00:00:00` fails there while being *required* elsewhere.

---

## Blocker 2 · `metric_definitions` field name

The generator emits `symptoms`. The engine reads `symptom_categories`.

```
generated:  {"metric_id": "request_latency_ms", "symptoms": ["latency increase"]}
engine:     metric.get("symptom_categories", [])      # case_fingerprint.py:188
```

**Consequence:** every case fingerprint has empty `symptom_categories`. Symptom
overlap is the highest-weighted similarity dimension at 0.26, so with it at
zero nothing can score. One field name silently disables the entire recall
path.

Rename `symptoms` → `symptom_categories`.

---

## Blocker 3 · Patterns and observations never share an entity

**This is the substantive one.** With blockers 1 and 2 fixed in memory, all 120
scenarios assess successfully — and all 120 return `0.000`, `LOW`, zero
candidates, no pattern.

The reason:

```
health_observations entity prefixes   {'SVC': 50000}      100% services
known_errors applies_to prefixes      {'COMP': 21, 'DATA': 23, 'VENDOR': 20,
                                       'INFRA': 16, 'POL': 16, 'CLOUD': 4}
```

**Every observation is raised on an `SVC-*` application service. Not one
pattern applies to a service.** The consequence, measured across all 100
patterns for each case:

```
best achievable similarity   max 0.318   median 0.310
similarity floor                         0.350
cases clearing the floor                 0 / 25
```

Four of the seven similarity dimensions are structurally pinned at zero:

| Dimension | Weight | Why zero |
|---|---|---|
| `same_entity` | 0.18 | No pattern applies to any observed entity |
| `declared_applicability` | 0.28 | 2,144 `APPLIES_TO` edges exist, none reaching an `SVC-*` |
| `entity_kind` | 0.06 | `APPLICATION_SERVICE` vs `SOFTWARE_COMPONENT` etc. |
| `structural_position` | 0.14 | Services depend on `INFRA-*`; components on `CLOUD-*` / `DATA-*`. No shared parents or dependencies |

That leaves symptom overlap (0.26) plus scraps — a ceiling of ~0.32 against a
floor of 0.35. **The dataset cannot recall anything, by construction.**

### Any of three fixes works

1. **Raise observations on the entity the pattern applies to.** Most faithful:
   a fault occurs on a component, and the observation is of that component.
2. **Add `APPLIES_TO` edges from patterns to the services above them.** The
   `declared_applicability` dimension is worth 0.28 alone and would clear the
   floor by itself when the symptom also matches.
3. **Give services and their components shared structural context** — common
   `parent_services` or `depends_on` — so `structural_position` contributes.

Option 1 is the smallest change and the most realistic. Option 2 additionally
demonstrates curated expert knowledge, which the demonstration wants.

**Do not lower the similarity floor.** 0.35 is calibrated against the working
fixtures; moving it to accommodate this would mask the topology problem and
degrade recall quality everywhere else.

---

## A note on `compatibility_validation.json`

The bundled self-check reports:

```json
"known_errors_recallable": true,
"scenarios_runnable": true,
"status": "PASS"
```

Neither holds. Nothing is recallable and no scenario produces an assessment.
The check is presumably verifying that patterns have admissible
`knowledge_status` and `trust_level` — which is true, all 100 are admissible —
rather than that any pattern can actually be reached by a case.

**Suggested replacement:** assert an outcome rather than a property.

```python
assessment = engine.assess(scenario_id)
assert assessment.candidate_assessments, "no pattern recalled"
assert assessment.confidence_score > 0
```

A check that passes on a dataset which cannot run is the failure mode worth
avoiding most, because it is indistinguishable from success until something
tries to use the data.

---

## What is already right

Worth stating plainly, because the remaining work is narrower than the list
above suggests:

- All references resolve — 2,000/2,000 entities in the graph, 92 referenced
  patterns all present
- Identifiers unique across every fixture
- No inverted validity windows, no record-ordering violations
- Private truth correctly absent from the export
- Manifest carries seed, version, counts and checksums
- `prior_confidence` omitted, strategy declared
- Scenarios emitted, problems and business_context present
- 13 relationship predicates including 2,144 `APPLIES_TO`

Blockers 1 and 2 are mechanical. Blocker 3 is a topology decision.

---

## Verification sequence

```
python -m synthetic_enterprise.validation.runner <dataset>
```

then, and this is the gate that matters:

```python
engine = OperationalConfidenceEngine(dataset, "config/confidence_policy.json")
for scenario in engine.scenarios[:50]:
    a = engine.assess(scenario["scenario_id"])
    assert a.candidate_assessments
```

Expect a spread of confidence across bands rather than a single value. If
every scenario returns the same number, something upstream is uniform that
should not be.

Then the 468 tests.

---

## Validator changes made during this review

Two, both because the validator was more permissive than the engine — the same
class of fault twice.

**Timestamp checking was tolerant.** It accepted ISO-8601 and passed a dataset
in which every timestamp was unreadable by the engine. Now checks the exact
per-field format, derived from the `strptime` call sites and confirmed against
the working fixtures.

**Relationship endpoints were checked against `entities.json` alone.** The
graph promotes known errors, changes, documents and observations into nodes,
so the validator reported 19 false errors on correct data.

A validator more permissive than the system it guards reports success on data
that cannot run. Both fixes are regression-checked against the shipped
fixtures, which still pass.
