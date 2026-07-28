# Data dictionary

## Observable zone

| File | Grain | Purpose |
|---|---|---|
| `entities.csv` | One enterprise entity | Business, service, application, component, resource, vendor, team, and policy inventory |
| `semantic_relationships.csv` | One typed graph edge | Dependency, routing, ownership, support, applicability, and modification topology |
| `known_errors.csv` | One operational pattern | Cause family, presentation declaration, action, efficacy, recurrence, and governance metadata |
| `health_observations.csv` | One initiating observation per episode | Metric breach available at the beginning of the run |
| `incidents.csv` | One incident per historical episode | User/system-visible operational impact; does not expose private root cause |
| `changes.csv` | One relevant change | Change evidence generated before affected incidents |
| `outcome_history.csv` | One decision/outcome per incident | Approval, modification, action, recovery, recurrence, and usefulness; `prior_confidence` is intentionally blank |
| `telemetry_samples.jsonl` | One detailed metric sample | Dense traces for golden/detailed episodes and ambiguity pairs |
| `runtime_evidence_events.jsonl` | One timed reveal event | Evidence that becomes available only after the ambiguity interval |
| `knowledge_documents.jsonl` | One source document | KB, runbook, problem, PIR, architecture, vendor, and wiki records |
| `document_chunks.jsonl` | One retrieval chunk | Chunked governed knowledge with inherited provenance and temporal availability |
| `vendor_advisories.jsonl` | One vendor status record | Authoritative synthetic vendor evidence |

## Private validation zone

| File | Grain | Purpose |
|---|---|---|
| `ground_truth_episodes.csv` | One causal episode | Actual cause, root, correct action, propagation targets, and independent random streams |
| `ambiguity_pairs.csv` | One matched pair | Identical observable prefix and timed distinguishing evidence contract |
| `counterfactual_pairs.csv` | One intervention pair | Fixed topology/background with an independently overridden cause |
| `causal_lineage.jsonl` | One field lineage assertion | Causal parents, generation mechanism, exogenous stream, and descendant status |
