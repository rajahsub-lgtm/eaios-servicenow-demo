# Cloud export notes

The generated repository uses CSV for relational records and JSONL for event/document streams so it runs without a compiled local dependency. For cloud deployment, convert the high-volume tables to Parquet after generation:

- `entities.csv`
- `semantic_relationships.csv`
- `incidents.csv`
- `health_observations.csv`
- `outcome_history.csv`
- `ground_truth_episodes.csv` (private validation zone only)

Recommended object-store partition keys:

- incidents/outcomes: `year`, `month`, `business_unit`, or `known_error_id`
- relationships: `relationship_type`
- document chunks: `document_type`, `published_year`
- telemetry: `event_date`, `metric_id`

Keep `private_truth/` in a separate bucket, account, schema, and access policy from `observable/`. The production reasoning workload should never receive credentials for the private validation zone.
