# EAIOS ServiceNow Storytelling Build — V1

## Scope lock

V1 demonstrates existing behavior only:

- stable evidence keeps confidence high;
- credible contradictory knowledge is accepted with limitations;
- confidence erodes from HIGH to MEDIUM;
- orchestration expands from accelerated validation to full investigation;
- completed work is preserved;
- agent participation grows from 3 to 6;
- accumulated outcomes mature confidence and produce an advisory automation-readiness signal;
- human approval remains enforced in every V1 path.

Human adjudication, confidence restoration, autonomous remediation, and removal of HITL are V2.

## Local validation

```powershell
python -m pytest -q
python demo_servicenow_storytelling.py
```

Expected test result:

```text
54 passed
```

Expected story contrast:

```text
Stable payment
HIGH 0.990 -> HIGH 0.990
ACCELERATED_VALIDATION -> ACCELERATED_VALIDATION
3 -> 3 agents
Automation readiness: CANDIDATE

Contradictory knowledge
HIGH 0.990 -> MEDIUM 0.770
ACCELERATED_VALIDATION -> FULL_INVESTIGATION
3 -> 6 agents
Automation readiness: SUSPENDED
KB-CONTRADICT-001: ACCEPTED_WITH_LIMITATIONS
```

## Existing assessment fields to add for storytelling

Use `outputs/servicenow_storytelling_assessment_fields.csv` as the exact field checklist.

Add these optional fields to `u_eaios_operational_assessment`:

| Label | Column | Type |
|---|---|---|
| Initial confidence score | `u_initial_confidence_score` | Decimal |
| Final confidence score | `u_final_confidence_score` | Decimal |
| Confidence trend | `u_confidence_trend` | Choice |
| Drift status | `u_drift_status` | Choice |
| Initial plan mode | `u_initial_plan_mode` | Choice |
| Final plan mode | `u_final_plan_mode` | Choice |
| Expanded during execution | `u_expanded_during_execution` | True/False |
| Initial agent count | `u_initial_agent_count` | Integer |
| Final agent count | `u_final_agent_count` | Integer |
| Plan revision reason | `u_plan_revision_reason` | String 4000 |
| Automation readiness | `u_automation_readiness` | Choice |
| Automation readiness rationale | `u_automation_readiness_rationale` | String 4000 |

Automation-readiness choices:

```text
NOT_READY
BUILDING_EVIDENCE
CANDIDATE
SUSPENDED
```

After creating the fields:

1. Run `python servicenow_field_discovery.py`.
2. Copy `config/servicenow_field_mapping.storytelling.template.json` over `config/servicenow_field_mapping.json`.
3. Set `confirmed=true` only for fields that discovery confirms.
4. Run the contradiction dry run.

```powershell
python servicenow_sync.py SCN-PAY-CONTRADICT-001 `
  --correlation-id EAIOS-DEMO-CONTRADICTION-001 `
  --dry-run
```

The mapped payload must still contain:

```text
approval = requested
u_outcome = Pending
```

## One child table for the visual timeline

Create:

```text
EAIOS Execution Event
u_eaios_execution_event
```

Use `outputs/servicenow_execution_event_fields.csv` as the field checklist.

This single child table supports:

- execution timeline;
- confidence change chart;
- before/after plan display;
- before/after agent count;
- skill and agent related list;
- event narrative.

Import data from:

```text
outputs/servicenow_execution_events.csv
```

The first import can be a normal Import Set and Transform Map. Resolve the parent assessment using Correlation ID.

## Native ServiceNow story layout

Arrange the Operational Assessment form in this order:

### 1. Executive summary

- Service
- Probable cause
- Initial confidence score
- Final confidence score
- Confidence trend
- Initial plan mode
- Final plan mode
- Initial agent count
- Final agent count
- Automation readiness
- Safety status
- Approval
- Outcome

### 2. Adaptive orchestration

- Expanded during execution
- Plan revision reason
- Recommended action
- Uncertainty factors

### 3. Knowledge and evidence

- Knowledge trust level
- Evidence status
- Evidence summary

### 4. Governance

- Human approval required
- Approval
- Safety status
- Outcome

### 5. Related list

- EAIOS Execution Events

## Native reports

Create these reports from `u_eaios_execution_event`:

1. **Confidence trajectory** — line chart
   - Group/order by Sequence
   - Value: Confidence after
   - Filter by Assessment

2. **Agent participation by scenario** — bar chart
   - Group by Agent name
   - Aggregate: Count
   - Filter by Assessment

3. **Execution event timeline** — list report
   - Sequence, Event type, Agent name, Skill ID, Summary

Create these reports from Operational Assessment:

4. **Automation readiness** — donut or bar
   - Group by Automation readiness

5. **Stable vs adaptive expansion** — list
   - Correlation ID, initial/final confidence, initial/final plan, initial/final agent count, readiness

## Final two records

### Stable evidence

```powershell
python servicenow_sync.py SCN-PAY-001 `
  --correlation-id EAIOS-DEMO-STABLE-001 `
  --live
```

### Contradictory knowledge

```powershell
python servicenow_sync.py SCN-PAY-CONTRADICT-001 `
  --correlation-id EAIOS-DEMO-CONTRADICTION-001 `
  --live
```

Expected contrast:

| Dimension | Stable | Contradictory knowledge |
|---|---|---|
| Confidence | HIGH 0.990 | HIGH 0.990 -> MEDIUM 0.770 |
| Plan | Accelerated | Accelerated -> Full Investigation |
| Agents involved | 3 | 6 |
| Knowledge | Trusted | Accepted with limitations |
| Readiness | Candidate | Suspended |
| Approval | Requested | Requested |
| Outcome | Pending | Pending |

## Demo statement

> EAIOS did not execute a fixed workflow. The same business goal began on the same high-confidence accelerated path. When credible but uncorroborated knowledge contradicted the established solution, the system accepted it only with limitations, reduced confidence, preserved completed work, added the skills needed for deeper investigation, selected additional qualified agents, suspended automation readiness, and retained the ServiceNow human-approval boundary.
