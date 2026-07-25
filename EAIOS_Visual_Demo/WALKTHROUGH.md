# Demonstration walkthrough

Target: **8–10 minutes**. Every figure below is produced by the run, not
written into the fixtures. Regenerate with `.\validate.ps1`.

The four scenarios are one progressive story, not a feature catalogue:

```
HOLD      stable evidence            smallest sufficient plan
ERODE     contradiction              confidence falls, investigation widens
RECOVER   explicit resolution        confidence partly returns, plan narrows
DISCOVER  cross-platform symptoms    vendors cleared, shared cause found
```

---

## 0 · Problem and boundary — 1 minute

Enterprise operations teams receive symptoms, not causes. Incidents arrive in
different queues, owned by different groups, describing different services.

**Scope, stated up front:** ServiceNow remains the system of record, the
approval surface, and the outcome-control boundary. This is an adaptive
orchestration layer that proposes; it never authorises. Human approval is
enforced in every path, and no scenario can remove it.

---

## 1 · HOLD — stable evidence · 30–45 seconds

**Scenario:** Payment connector — stable evidence

```
confidence  0.990 HIGH -> 0.990 HIGH
plan width  3 -> 3 (peak 3) · 3 agents contributed
path        ACCELERATED_VALIDATION
readiness   CANDIDATE · approval REQUESTED
```

Strong outcome-validated confidence selects the smallest governed plan. No
unnecessary investigation is invoked.

**The point:** more agents are not automatically better. Establish confidence,
plan width, and the approval boundary here — then move on. Do not deep-dive.

---

## 2 · ERODE and RECOVER — two chapters, one story · 3–4 minutes

### Chapter A — confidence erodes

**Scenario:** Payment connector — contradictory knowledge

```
confidence  0.990 HIGH -> 0.770 MEDIUM
plan width  3 -> 5 (peak 5) · 6 agents contributed
path        ACCELERATED_VALIDATION -> FULL_INVESTIGATION
readiness   SUSPENDED · approval REQUESTED
conflicts   active 1 · resolved 0
```

Credible contradictory knowledge appears. It is **not** promoted to truth and
**not** discarded — it is accepted as evidence that uncertainty exists.

- The penalty applies in full: 0.22
- A hard flag is raised, and while it stands no credit can be applied
- Automation readiness moves to SUSPENDED
- The investigation widens; completed work is retained

### Chapter B — evidence resolves the contradiction

**Scenario:** Payment connector — contradiction resolved

```
confidence  0.990 HIGH -> 0.870 HIGH
plan width  3 -> 3 (peak 5) · 6 agents contributed
path        ACCELERATED_VALIDATION -> FULL_INVESTIGATION -> ACCELERATED_VALIDATION
readiness   BUILDING_EVIDENCE · approval REQUESTED
conflicts   active 0 · resolved 1
```

Deeper investigation retires the alternative explanation.

**Open the Evidence tab.** The knowledge record is byte-identical to Chapter A
— still `ACCEPTED_WITH_LIMITATIONS`, still `Material Contradiction`. The
resolution sits beneath it as a separate adjudication naming the skill that
triggered it and its effect on confidence.

> The platform never rewrites history to agree with its conclusion. It records
> a separate, auditable decision explaining why the evidence no longer blocks
> the current answer.

**Note what did not happen:** confidence recovered to 0.870, not 0.990.
Recovery is capped at 0.10 per reassessment while a contradiction costs 0.22.
Cycling erodes; it never restores. Readiness is BUILDING_EVIDENCE, not
automation-ready.

**Peak width 5 with final width 3** is why plan width and agent participation
are reported separately — the excursion is visible even though the plan
returned to where it started.

---

## 3 · DISCOVER — cross-platform capstone · 4 minutes

**Scenario:** GitHub and Teams — shared gateway dependency

### Start with the human problem

> Developers cannot reliably clone or push to enterprise repositories. At
> roughly the same time, employees cannot join Teams meetings. The incidents
> land in two different support queues and look unrelated.

Four incidents, two assignment groups: Developer Platform Support and
Workplace Technology Support.

### Then the investigation

```
confidence  0.823 MEDIUM -> 0.923 HIGH
plan width  6 -> 4 (peak 6) · 7 agents contributed
path        FULL_INVESTIGATION -> ACCELERATED_VALIDATION
readiness   BUILDING_EVIDENCE · approval REQUESTED
```

1. **Vendor status is unknown**, and that is derived from the graph — the
   service depends on external vendors, so their status starts unestablished.
   The flag blocks the accelerated path.
2. **Vendor Health Agent** establishes GitHub and Microsoft each healthy, from
   fresh authoritative sources. A stale snapshot and a crowd-sourced report are
   both rejected and remain visible with their reasons.
3. **External hypotheses are retired independently** — GitHub's evidence never
   speaks for Microsoft.
4. **Graph traversal starts from the GitHub trigger** and reaches Teams
   signalling, the shared secure web gateway, and its TLS inspection policy.
5. **A recent high-risk change** modified that policy.
6. **Internal telemetry** shows failure on the inspected path while an exempt
   route stays healthy.
7. Confidence recovers, the plan narrows, and the unneeded fusion step is
   **cancelled before it runs**.

### The line that carries it

> The graph did not confirm a cause already written into the scenario. It
> computationally discovered the convergence between two apparently unrelated
> services.

If challenged, the fixture's `primary_component_id` is the GitHub component;
the gateway appears nowhere in the scenario definition. A test asserts this:
`test_the_scenario_does_not_name_its_own_answer`.

### Governance close

Readiness is BUILDING_EVIDENCE with two blockers, and both are real: recent
success 0.90 against a 0.95 threshold, recurrence 0.10 against 0.05. The
control profile is complete — the rollback is reversible, its blast radius
bounded but cross-platform, and three controls are required including
cross-platform verification.

**Approval is requested. Outcome is Pending. Nothing executed.**

---

## 4 · Productionisation and ServiceNow fit — 1 minute

- 253 tests; V1 outputs frozen throughout the build
- Policy-driven: confidence, orchestration modes, readiness, vendor trust and
  runtime signals are all configuration, not code
- ServiceNow mapping is field-discovered, with approval and outcome modelled
  as separate concepts
- Not claimed: licensed Workflow Data Fabric, ServiceNow Knowledge Graph, or
  AI Agent Studio capabilities

---

## Timing

| Section | Target |
|---|---|
| Problem and boundary | 1:00 |
| HOLD | 0:45 |
| ERODE and RECOVER | 3:30 |
| DISCOVER | 4:00 |
| Productionisation | 1:00 |
| **Total** | **10:15** |

Trim HOLD to 30 seconds and the productionisation close to 45 seconds for a
9-minute run.

## Before presenting

```powershell
.\validate.ps1          # regenerate artifacts, confirm the suite is green
.\run_demo.ps1 -SkipInstall
```

**Decide in advance** whether the live PDI is part of the main flow or held
back as the answer to "is this really integrated?". Opening ServiceNow adds
1–2 minutes and is the only step with external failure risk. The dry run
proves the mapping without leaving the machine:

```powershell
python servicenow_sync.py SCN-CROSS-GATEWAY-001 `
  --correlation-id EAIOS-DEMO-CROSS-GATEWAY-001 --dry-run
```
