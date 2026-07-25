# EAIOS Visual Demo

Standalone, synthetic visual demonstration of adaptive EAIOS reasoning.

## Architectural boundary

- ServiceNow remains the operational system of record and approval surface.
- Python performs graph traversal, evidence fusion, confidence assessment, and adaptive orchestration.
- Streamlit is a read-only explanatory layer.
- All included data is synthetic.
- Human approval remains required for consequential actions.

This folder intentionally excludes the legacy API server, unrelated demo entry points, generated
output snapshots, and earlier starter packages. The small ServiceNow boundary required for the PDI
and Flow Designer demonstration is included.

## Quick start

```powershell
.\run_demo.ps1
```

The launcher creates a local virtual environment, installs the pinned dependency ranges, regenerates
the visual-story artifacts, validates them, and starts Streamlit.

To validate without starting a server:

```powershell
.\validate.ps1
```

## Direct commands

```powershell
python -m pip install -r requirements.txt
python demo_servicenow_storytelling.py
python -m pytest -q
python -m streamlit run eaios_story_app.py
```

## ServiceNow PDI and Flow Designer

No credentials are stored in this project. Start with the environment-variable names in
`config/servicenow.env.template` and the build sequence in `SERVICENOW_STORYTELLING_BUILD.md`.

Validate the payload and mapping without contacting ServiceNow:

```powershell
python servicenow_sync.py SCN-PAY-001 `
  --correlation-id EAIOS-DEMO-STABLE-001 `
  --dry-run
```

After the PDI table and fields exist, discover its dictionary fields:

```powershell
python servicenow_field_discovery.py
```

Field discovery creates a suggestion file only. Review it and explicitly confirm the mapping before
using live sync. Live synchronization remains correlation-keyed and is never run by `run_demo.ps1`.

The story generator also creates CSV artifacts under `outputs/` for ServiceNow import and Flow
Designer trigger demonstrations.

## Contents

- `eaios_story_app.py` — Streamlit presentation.
- `eaios_story_data.py` — presentation data access and transformations.
- `demo_servicenow_storytelling.py` — deterministic artifact generator.
- `config/` — confidence, orchestration, access, readiness, and display policies.
- `json/` — explicitly synthetic source records.
- `outputs/` — generated at runtime.
- `servicenow_sync.py` — explicit dry-run or live assessment synchronization.
- `servicenow_field_discovery.py` — PDI dictionary inspection and mapping suggestions.
- `servicenow_table_client.py` — minimal standard-library Table API client.
- `SERVICENOW_STORYTELLING_BUILD.md` — PDI fields, forms, reports, and flow sequence.

The current story retains the stable and contradictory payment examples as a regression baseline.
Teams, GitHub, and shared-dependency scenarios can be added without restoring the removed legacy
entry points.
