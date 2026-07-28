# Validation findings — generated enterprise

**Datasets checked:** `generated/golden` (120 entities) and
`generated/enterprise` (2,000 entities), generator 1.0.0, seed 20260728.

**Headline:** the enterprise is internally coherent and the causal machinery
works. It **cannot be read by the engine it was generated for** — every
fixture uses a different vocabulary. This is a schema contract failure, not a
modelling failure, and it is entirely fixable by an exporter.

---

## 1 · What passes

| Check | Result |
|---|---|
| Causal ordering across 800 golden episodes | **all hold** the full change → fault → symptom → incident → decision → action → recovery sequence |
| Timestamp parseability | clean |
| Validity windows | clean |
| Identifier uniqueness | clean except `sample_id` (§3) |
| `prior_confidence` | **omitted**, and the manifest declares `prior_confidence_strategy: OMIT` |
| Two-world separation | observable and private truth are in separate trees |
| Manifest | seed, version, counts, checksums and policy all recorded |
| Adversarial and counterfactual scaffolding | 24 ambiguity pairs, 12 counterfactual pairs, 576 causal-lineage records present |

The causal ordering result is the significant one. Eight hundred episodes with
no ordering violation means the episode simulator is doing what it was
designed to do.

---

## 2 · Blocking · the engine cannot load the data

The definitive test, run against the production loader with no field
translation:

```
GRAPH FAILED:  KeyError: 'subject_entity_id'
ENGINE FAILED: KeyError: 'subject_entity_id'
```

The generator emits its own vocabulary. Every fixture diverges.

### Renames — same meaning, different name

| Fixture | Engine reads | Generator emits |
|---|---|---|
| `semantic_relationships` | `subject_entity_id` | `source_entity_id` |
| `semantic_relationships` | `object_entity_id` | `target_entity_id` |
| `semantic_relationships` | `predicate` | `relationship_type` |
| `semantic_relationships` | `status` | `lifecycle_status` |
| `entities` | `status` | `lifecycle_status` |
| `telemetry_samples` | `sample_id` | `telemetry_id` |

### Fields the engine requires that are absent

| Fixture | Missing |
|---|---|
| `entities` | `description`, `environment`, `external_service_id`, `owner`, `source_system`, `status` |
| `semantic_relationships` | `direction`, `provenance`, `source_system`, `valid_from`, `valid_to` (plus the four renames) |
| `known_errors` | `title`, `probable_cause`, `hypothesis_class`, `historical_occurrences`, `historical_success_rate_numeric`, `recent_failure_signal`, `average_resolution_minutes`, `requires_human_approval`, `external_service_id` |
| `incidents` | `known_error_id`, `business_capability`, `correlation_id`, `description`, `resolved_at`, `resolution_notes`, `scenario_id`, `external_service_id` |
| `changes` | `short_description`, `summary`, `owner`, `planned_start`, `planned_end`, `is_recent`, `scenario_id`, `external_service_id` |
| `health_observations` | `metric_name`, `current_value`, `threshold_value`, `threshold_breached`, `observation_summary`, `service_name`, `source_record_id`, `requires_enterprise_reasoning`, `scenario_id`, `external_service_id` |
| `knowledge_documents` | `body`, `status`, `owner`, `recommended_action`, `content_safety_status` |
| `telemetry_samples` | `metric_name`, `unit`, `threshold_value`, `severity`, `environment`, `region`, `correlation_id`, `trust_level`, `source_system`, `scenario_id`, `external_service_id` |
| `vendor_advisories` | `vendor`, `service`, `summary`, `applies_to_entity_ids` |

### Fixtures the engine requires that are not emitted at all

`scenarios`, `problems`, `business_context`, `metric_definitions`

`scenarios` is the critical one — it is the entry point. Without it there is
nothing to assess.

### Fields that are not cosmetic

Some absences change behaviour rather than shape:

- **`knowledge_documents.status` and `content_safety_status`** — documentation
  eligibility requires `Published` and `SAFE`. Absent, every document is
  ineligible and the documented-reasoning path never fires.
- **`knowledge_documents.body`** — the proposed cause is drawn from it.
- **`known_errors.hypothesis_class`** — separates internal from external
  hypotheses in fusion.
- **`semantic_relationships.valid_from` / `valid_to`** — admissibility filters
  on the window; absent, relationships may be permanently invisible.
- **`incidents.known_error_id`** — without it no incident links to a pattern.
- **`health_observations.threshold_breached` / `current_value`** — the trigger
  observation drives the whole assessment.

---

## 3 · Errors found by the coherence validators

| Rule | Finding |
|---|---|
| `referential·identity_present` | 1,284 telemetry rows have no `sample_id` — it is `telemetry_id` |
| `referential·topology_coverage` | 100% of entities have no relationships, because endpoints are named `source_entity_id` / `target_entity_id` |

Both are consequences of §2 rather than independent faults. Neither indicates
an incoherent enterprise.

---

## 4 · Not yet checked

These need the schema fixed first, because they cannot run until the engine
can load the data:

- **The 468 existing tests** — the strongest available gate, since they encode
  the semantic contracts the layers rely on
- **Long-tail distribution** — whether outcomes-per-pattern actually produce
  the intended maturity spread rather than clustering above
  `minimum_outcome_sample` (15)
- **Adversarial leakage probes** — feature audit, trivial-classifier probe,
  grouped splits
- **Transferred-experience share** — the target of at least 20% of evaluations
  using transferred rather than direct experience
- **Non-diagnosis share** — the target of at least 10% reaching governed
  non-diagnosis or documentation-only

---

## 5 · Recommended fix

**Write the compatibility exporter as its own module**, rather than changing
the generator's internal vocabulary.

The generator's names are arguably better — `source`/`target` is clearer than
`subject`/`object`, and `relationship_type` clearer than `predicate`. The
engine's names are a fixed contract with 468 tests behind them. An exporter
keeps both, makes the mapping explicit and reviewable, and is the natural
place to fail loudly when a required field has no source.

```
generator/exporters/demo_fixtures.py
    map field names
    synthesise required fields that have a source
    FAIL LOUDLY on required fields with no source — do not default them
```

**Do not fill missing fields with plausible defaults.** A defaulted
`threshold_breached` or `content_safety_status` produces a dataset that loads
and reasons wrongly, which is worse than one that refuses to load.

### Suggested order

1. Emit `scenarios` — without it nothing can be assessed
2. Rename the six fields in the table above
3. Add the behaviour-changing fields listed in §2
4. Re-run these validators
5. Run the 468 tests against the exported fixtures — that is the real gate
6. Then the statistical and adversarial suites

---

## 6 · A note on what this does not say

The enterprise model looks sound. Eight hundred episodes with correct causal
ordering, a clean two-world split, a manifest with checksums, and ambiguity
and counterfactual pairs already generated is substantial and hard work that
is visibly done.

The finding is narrow: the compiler and the engine disagree about field names,
and nothing in the pipeline noticed because nothing had tried to load one with
the other. That is exactly what a validator run before the exporter exists is
for.
