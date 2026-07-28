# Generator modifications — exact change list

Against `generated/golden` and `generated/enterprise`, generator 1.0.0.

The enterprise model is sound. The compiler and the engine disagree about
field names, and nothing noticed because nothing had tried to load one with
the other.

**Recommendation: do not change the generator's internal vocabulary.** Its
names are better — `source`/`target` beats `subject`/`object`. Add an exporter
that translates, so the mapping is explicit, reviewable, and has one place to
fail loudly when a required field has no source.

```
generator/exporters/demo_fixtures.py
```

---

## Tier 1 · Required — the engine raises KeyError without these

Determined by scanning for `row["field"]` rather than `row.get("field")`.
Absence is not a degradation; it is a crash.

### semantic_relationships

| Engine requires | Source |
|---|---|
| `subject_entity_id` | rename from `source_entity_id` |
| `object_entity_id` | rename from `target_entity_id` |
| `predicate` | rename from `relationship_type` |
| `relationship_id` | already present |

### known_errors

| Engine requires | Source |
|---|---|
| `known_error_id`, `applies_to_entity_id`, `symptom_category` | present |
| `title` | pattern library — short human name |
| `historical_success_rate_numeric` | **derive from `outcome_history`** (see Coherence) |
| `recent_failure_signal` | `LOW` / `MEDIUM` / `HIGH`, derived from recent outcomes |

### outcome_history

| Engine requires | Source |
|---|---|
| `known_error_id`, `entity_id`, `outcome`, `recorded_at` | present |
| `evidence_usefulness_score` | integer 0–100 |
| `recovery_minutes` | numeric |

### incidents

| Engine requires | Source |
|---|---|
| `incident_id`, `opened_at`, `entity_id` | present |
| `short_description` | generated summary text |
| `state` | e.g. `Resolved`, `In Progress` |

### changes

| Engine requires | Source |
|---|---|
| `change_id`, `entity_id`, `implemented_at` | present |
| `risk` | `Low` / `Medium` / `High` |

### telemetry_samples

| Engine requires | Source |
|---|---|
| `sample_id` | rename from `telemetry_id` |
| `entity_id`, `metric_id`, `observed_at`, `value` | present |
| `metric_name`, `unit` | join from `metric_definitions` |
| `trust_level` | `TRUSTED` |
| `source_system` | e.g. `Synthetic OpenTelemetry` |

### vendor_advisories

| Engine requires | Source |
|---|---|
| `advisory_id`, `published_at` | present |
| `vendor`, `service` | vendor entity name and service |
| `status` | `Investigating` / `Resolved` / `Operational` |
| `incident_confirmed` | boolean |
| `confidence` | 0.0–1.0 |
| `source_authority` | e.g. `VENDOR_STATUS_PAGE` |

### problems

`problem_id` — the fixture is not emitted at all.

### scenarios

**Not emitted, and nothing can run without it.** The engine resolves a
scenario to a trigger observation and assesses from there.

| Required | Source |
|---|---|
| `scenario_id` | one per golden episode |
| `trigger_observation_id` | the observation that opens the episode |
| `name`, `description` | generated |
| `primary_component_id` | the affected entity |

Scenario rows may also carry `expected_confidence` and similar. **The engine
ignores them by design** — they document intent and are never read.

---

## Tier 2 · Behaviour-changing — no crash, silent capability loss

The dangerous ones. Read with `.get()`, so the data loads, the run completes,
and an entire reasoning path never fires.

| Fixture · field | Absent means |
|---|---|
| `knowledge_documents.status` | must be `Published` or the document is ineligible — **every** documented-reasoning path dies |
| `knowledge_documents.content_safety_status` | must be `SAFE`, same consequence |
| `knowledge_documents.body` | the proposed cause is drawn from it |
| `knowledge_documents.recommended_action` | the recommendation text |
| `knowledge_documents.owner` | named in the disclosure — "owned by X" |
| `known_errors.hypothesis_class` | `EXTERNAL_VENDOR_OUTAGE` is compared explicitly; absent, vendor hypotheses are never retired |
| `known_errors.knowledge_status` / `trust_level` | admissibility filters on `Active`/`Provisional` and `Trusted`/`Provisional` — absent, **nothing is recallable at all** |
| `known_errors.valid_from` / `valid_to` | validity window filter |
| `semantic_relationships.relationship_authority` | traversal filters to `AUTHORITATIVE`; absent, no path is authoritative |
| `semantic_relationships.confidence` | traversal thresholds |
| `semantic_relationships.status` | rename from `lifecycle_status` |
| `health_observations.threshold_breached` / `current_value` / `threshold_value` | the trigger's breach state |
| `incidents.known_error_id` | links an incident to a pattern — see design note |
| `entities.service_provider_type` | `EXTERNAL_VENDOR` drives vendor-dependency discovery |
| `entities.status` | rename from `lifecycle_status` |
| `outcome_history.approval_decision` / `human_modification` | provenance is **derived** from these |
| `outcome_history.recurrence_within_24h` | recurrence rate |
| `outcome_history.scenario_pattern` | carried through feedback |

**`approval_decision` and `human_modification` deserve emphasis.** Provenance
is not stored — it is derived at read time. No `human_modification` means no
`HUMAN_VERIFIED` cases, which means the provenance weights (1.2 / 1.0 / 0.8),
the supervision penalty, and the "human correction outranks bare approval"
argument all become invisible, with nothing reporting the loss.

---

## Tier 3 · Cosmetic — never read by any code path

Determined by scanning, not assumed: `is_recent`,
`requires_enterprise_reasoning`, `historical_occurrences`,
`average_resolution_minutes`, `requires_human_approval`,
`external_service_id`, `source_record_id`, `description`,
`resolution_notes`, `summary`, `planned_start`, `planned_end`,
`correlation_id` on incidents, `region`, `environment`, `severity` on
telemetry.

Worth emitting for realism in the UI; they cannot break anything.

---

## Coherence requirements the exporter must enforce

### Derived summaries must agree with what they summarise

`known_errors.historical_success_rate_numeric` and `recent_failure_signal`
are observable summaries. If written independently of `outcome_history`, the
dataset contradicts itself — a pattern advertising 95% success whose outcomes
show 40%.

Derive them at export time, after outcomes exist. Add a validator asserting
agreement within tolerance.

### Fail loudly, never default

Do not fill a missing Tier 1 or Tier 2 field with a plausible default. A
defaulted `content_safety_status` produces a dataset that loads and reasons
wrongly, which is strictly worse than one that refuses to load.

```python
raise ExportError(
    f"{fixture}.{field} is required by the engine and has no source "
    f"in the generated model"
)
```

---

## Two design questions worth deciding explicitly

### `incidents.known_error_id` — suspected or true?

Your spec says *do not automatically assign the true root cause to the
incident.* Correct — but the engine reads this field.

Suggested: populate it with the pattern **the investigation concluded**, not
the hidden truth, and leave it empty for episodes never resolved, misdiagnosed
or reaching non-diagnosis. That preserves the two-world split, gives the
engine a link, and creates the honest case where the recorded pattern is
wrong — which the demonstration benefits from containing.

### Scenario count

One per golden episode is right for the ten to twenty traceable ones. Fifty
thousand would make the picker unusable. Suggest emitting scenarios for the
golden tier only, letting the rest exist purely as history.

---

## Suggested order

1. **`scenarios`** — nothing runs without it
2. **Six renames** — subject / object / predicate / status ×2 / sample_id
3. **Tier 1** — the crash set
4. **Tier 2** — the silent-loss set
5. `python -m synthetic_enterprise.validation.runner generated/golden`
6. **Run the 468 tests against the exported fixtures — the real gate**
7. Then statistical and adversarial suites

Steps 1–4 are mechanical. Step 6 is where you find out whether the enterprise
is genuinely coherent, because those tests encode the semantic contracts the
layers depend on.
