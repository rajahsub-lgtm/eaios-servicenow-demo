# Generator fixes for v1.3 — complete list

Everything found in v1.2, including checks run **ahead** of the blockers to
avoid another round trip. Six fixes. Three are one-line vocabulary changes
that each silently disable a whole capability.

**The theme:** v1.2's *structure* is right. What is left is almost entirely
**vocabulary** — the generator's words are reasonable and the engine's are
different, and the engine compares strings exactly.

---

## A · `outcome` vocabulary — every case reads as a failure

```
v1.2 emits:    RESOLVED (38,113) · NOT_RESOLVED (8,647) · NOT_EXECUTED (3,240)
engine tests:  row["outcome"] == "Successful"        experience_ledger.success_rate

rows matching: 0 of 50,000
```

Every `weighted_success_rate` is 0.0. Even with every other fix applied, each
pattern looks like a total failure — and `REMEDY_PREVIOUSLY_INEFFECTIVE`
fires on all of them, costing 0.30 and barring the narrow plan everywhere.

**This is the single highest-impact fix.**

| v1.2 | Engine vocabulary |
|---|---|
| `RESOLVED` | `Successful` |
| `NOT_RESOLVED` | `Unsuccessful` |
| `NOT_EXECUTED` | `Unsuccessful` — the recommendation was declined and never carried out. **Not** a success |

The engine also recognises `Failed` and `Partially Successful` if you want a
richer spread; only `Successful` is tested for exact equality.

---

## B · Scenarios sit at the beginning of history

Unchanged from the v1.2 report and still the structural one.

```
scenario times   2024-01-01 .. 2024-01-10
outcome times    2024-01-01 .. 2025-08-13

median scenario has 0.8% of the corpus behind it
```

**Draw scenarios from the END of the generated period.** The engine counts
only outcomes recorded on or before the assessment, which is correct — a case
cannot learn from its own future.

---

## C · Knowledge document `trust_level` — every document excluded

```
v1.2 emits:  TRUSTED (1,905) · CONDITIONAL (595)
engine map:  {"Trusted": 1.0, "Provisional": 0.6, "Unverified": 0.25, "Deprecated": 0.0}

lookup("TRUSTED") -> 0.0
documented_reasoning: "if trust <= 0.0: continue"
```

**All 2,500 documents are excluded from every assessment.** This is why
`MISSING_GOVERNED_KNOWLEDGE` raises on every case, costing 0.10 and barring
the narrow plan.

| v1.2 | Engine |
|---|---|
| `TRUSTED` | `Trusted` |
| `CONDITIONAL` | `Provisional` (0.6) or `Unverified` (0.25) — your choice of severity |

Capitalisation only. `status: Published` and `content_safety_status: SAFE` are
already correct.

### C2 · `document_type` also mismatches

| v1.2 | Engine | Weight |
|---|---|---|
| `KNOWLEDGE_ARTICLE` | `KB` | 0.9 (currently defaults to 0.3) |
| `POST_INCIDENT_REVIEW` | `PIR` | 0.8 (currently 0.3) |
| `VENDOR_ADVISORY` | — no mapping; use `KB` or add to policy | 0.3 |
| `RUNBOOK` | `RUNBOOK` | 1.0 — already correct |

Not fatal — unmapped types fall back to 0.3 rather than being excluded — but
it flattens the document-quality ranking that documented reasoning exists to
demonstrate.

---

## D · Two `knowledge_documents` fields are lists, not delimited strings

```
AttributeError: 'list' object has no attribute 'split'
```

| Field | Engine wants |
|---|---|
| `knowledge_documents.entity_ids` | `"APP-0051,SVC-0051"` |
| `knowledge_documents.symptom_categories` | `"PAYMENT_TIMEOUT,CONNECTOR_SATURATION"` |

**Note the asymmetry:** `metric_definitions.symptom_categories` must stay a
**list**. Same field name, different representation, because two engine code
paths read it differently. That is an engine wart worth fixing later; match
the fixtures for now.

These are the only two type mismatches across every shared field.

---

## E · RAG chunks are missing the eligibility metadata

`document_chunks` carries `chunk_id`, `document_id`, `document_type`,
`entity_ids`, `known_error_ids`, `published_at`, `text`, `trust_level`.

The governed retriever needs six more, inherited from the source document:

| Missing | Why it is needed |
|---|---|
| `symptom_categories` | The entity-and-symptom test that decides whether a chunk may support a cause |
| `content_safety_status` | Absolute gate — unsafe material is excluded regardless of relevance |
| `last_validated_at` | Freshness decay |
| `title` | Retrieval ranking and disclosure |
| `source_id` | Which document a chunk came from, for the ledger |
| `source_type` | Reported in the evidence ledger |

Without these the chunks can be embedded and searched but **cannot be
governed** — which is the entire point of the retrieval layer. Chunks should
inherit trust, timestamps, safety status and covered entities from their
source document.

Format for reference — `json/rag_corpus.jsonl` in the demo repository.

---

## F · 800 scenarios is unusable as a picker

The demonstration selects a scenario from a dropdown. Eight hundred entries
makes it unnavigable.

**Emit scenarios for the golden tier only** — ten to twenty fully traceable
episodes. The other 49,980 episodes should still exist as history; they simply
do not each need an entry point.

---

## What is already right — do not change it

| | |
|---|---|
| **Long-tail distribution** | 8% of patterns with no outcomes, 18% under 5 cases, 23% with 5–14, 25% established, 26% mature. Max 4,061, median 31. This is genuinely long-tailed and lands close to the target |
| **Approval variance** | 46,760 approved, 3,240 rejected |
| **Human modification** | 16.8% — `HUMAN_VERIFIED` provenance is reachable |
| **Timestamps** | Correct per-field, both formats |
| **`metric_definitions.symptom_categories`** | Present and correctly a list |
| **Pattern/observation alignment** | Fixed — recall reaches patterns, `DIRECT` and `TRANSFERRED` both appear |
| **Document status and safety** | `Published` / `SAFE` throughout |
| **Referential integrity** | All references resolve, identifiers unique |

---

## Two gaps worth a decision rather than a fix

### `PEER_AGENT` provenance is unreachable

```
outcomes with established_by_agent: 0
```

`SELF_OUTCOME` and `HUMAN_VERIFIED` are both reachable; the third class is
not. The provenance weighting (1.2 / 1.0 / 0.8), the standing rule, and the
attenuation ceiling therefore have nothing behind them.

A few hundred outcomes carrying `established_by_agent` and
`established_for_domain` would make that demonstrable — and one or two
deliberately **outside** the agent's registered domain would show the standing
clamp, which is one of the sharper governance points.

### Derived summaries disagree with their own outcomes

90 of 92 patterns advertise a `historical_success_rate_numeric` that differs
from their recorded outcomes by more than ten points — several claim 100%
against 0% actual.

Most of this will resolve when fix **A** lands, since the actual rate is
currently computed against a vocabulary that never matches. **Re-derive these
at export time, after outcomes exist**, and add an assertion that they agree
within tolerance. A pattern advertising 95% whose outcomes show 40% is
self-contradicting data that passes every referential check.

---

## Suggested order

1. **A** — outcome vocabulary. Highest impact, smallest change
2. **C** — `trust_level` capitalisation, and `document_type` mapping
3. **D** — two fields to delimited strings
4. **B** — move scenarios to the end of the timeline
5. **F** — golden-tier scenarios only
6. **E** — chunk metadata, needed for Phase 3 rather than for the engine

A, C and D are string changes. B is a selection change. Together they should
produce the confidence spread everything else has been waiting on.

---

## Verification

```bash
python -m synthetic_enterprise.validation.runner <dataset>
```

Then the gate — and it is about **spread**, not just count:

```python
scores = [engine.assess(s["scenario_id"]).confidence_score
          for s in engine.scenarios[:50]]
assert max(scores) > 0.5,  "no scenario reaches usable confidence"
assert len({round(s, 1) for s in scores}) > 3, "no spread — something is uniform"
```

Then the 472 tests.
