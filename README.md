# EAIOS Synthetic Enterprise Repository

Deterministic synthetic enterprise data generator for cloud-scale EAIOS testing.

## Profiles

- `golden`: small, fully traceable dataset for development and inspection.
- `enterprise`: 2,000 entities, 15,000 relationships, 50,000 incidents/outcomes, and 20,000 document chunks.

## Core guarantees

- Hidden ground truth is stored separately from observable records.
- Causes generate downstream telemetry, incidents, decisions, and outcomes.
- `prior_confidence` is omitted from generated outcomes to prevent circularity.
- Experience is long-tailed across patterns and pattern/entity combinations.
- Matched ambiguity pairs have byte-equivalent canonical observable prefixes and diverge only after a timed reveal.
- Counterfactual worlds preserve topology, background conditions, and exogenous noise while changing only the cause and its descendants.
- Every record is marked `SYNTHETIC`.

## Generate

```bash
python -m generator.cli generate --profile golden --output generated/golden
python -m generator.cli generate --profile enterprise --output generated/enterprise
```

## Validate

```bash
python -m generator.cli validate --dataset generated/enterprise
```

## Outputs

- `observable/`: data available to EAIOS.
- `private_truth/`: generator-only causal truth and lineage.
- `reports/`: structural, causal, temporal, statistical, and leakage validation.
- `manifest.json`: counts, versions, seed, and checksums.
