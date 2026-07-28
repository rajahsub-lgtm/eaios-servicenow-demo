# Synthetic repository quality report

## Enterprise profile

- 2,000 entities
- 15,000 typed relationships
- 100 known-error patterns
- 50,000 incidents
- 50,000 linked outcomes
- 2,500 source documents
- 20,000 document chunks
- 24 matched ambiguity pairs
- 12 counterfactual pairs

## Passed invariants

- Every reference resolves and all primary identifiers are unique.
- Every record exposed to the reasoning system is marked `SYNTHETIC`.
- Private causal truth is stored outside the observable zone.
- `prior_confidence` is blank on all generated outcomes.
- Observations precede incidents; changes precede affected incidents; outcomes follow incidents; PIRs follow outcomes.
- Rejected recommendations are not recorded as executed.
- Every matched ambiguity pair has an exactly equal canonical pre-reveal telemetry prefix.
- Distinguishing evidence becomes available only after the ambiguity interval.
- Counterfactual pairs use the same background stream while the cause changes.
- Experience remains long-tailed: 8 patterns with no cases, 18 with 1–4, 23 with 5–14, 21 with 15–99, and 30 with 100+.

## Adversarial leakage probe

Observable pre-decision metadata only:

- Majority baseline: 0.331
- Shallow decision tree accuracy: 0.380
- Logistic-regression accuracy: 0.379
- Release ceiling: 0.650

Identifiers, outcomes, post-reveal evidence, and private truth were excluded from the probe.

## Storage note

This build uses CSV and JSONL for portability in the current runtime. Convert high-volume relational files to Parquet in the target cloud environment and maintain separate security boundaries for observable and private-truth zones.
