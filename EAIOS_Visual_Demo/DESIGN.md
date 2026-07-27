# EAIOS demonstration — architecture design document

**Status:** built and tested · 468 tests · branch `experience-transfer`
**Scope:** the ServiceNow-facing demonstration of EAIOS 2/3 governance concepts
**Companions:** `ARCHITECTURE.md` (summary), `DEMO_SCRIPT.md` (walkthrough),
`ARCHITECTURE_REVIEW.md` and `ARCHITECTURE_PLAN.md` (the correction that
produced the current layer boundaries)

---

## 1 · Purpose and scope

### 1.1 What this system is

A working operational-reasoning system that ingests a health observation about
an enterprise service and produces a governed recommendation. It demonstrates
that:

- confidence can be **derived** from recorded outcomes rather than asserted;
- the investigation **plan** can be a consequence of that confidence, adjusted
  while the run is in flight;
- governance can sit **inside** the reasoning loop rather than at its exit.

### 1.2 What it is not

It is not a remediation system. Nothing it produces executes against a live
estate; every path terminates in a recommendation requiring human approval.
ServiceNow remains the system of record and the approval control.

All data is synthetic and marked `data_classification: SYNTHETIC` at the
record level.

### 1.3 Relationship to EAIOS

EAIOS 2 defines the architecture and governance; EAIOS 3 is the engineering
line. This demonstration is a deliberately lightweight wrapper that illustrates
the governance principles against a concrete, recognisable use case. It does
not reproduce EAIOS 2 in full.

---

## 2 · System context

```
        ServiceNow (system of record, approval control)
                          ▲
                          │ assessment record, escalation
                          │
   ┌──────────────────────┴───────────────────────────┐
   │              EAIOS demonstration                 │
   │                                                  │
   │   observation ──▶ confidence ──▶ plan ──▶ agents │
   │        ▲              │            │        │    │
   │        │              └── runtime reassessment    │
   │        │                                     │    │
   │   synthetic fixtures ◀────── outcome feedback ┘   │
   └──────────────────────────────────────────────────┘
```

**Inbound:** a `health_observation` naming an entity, a metric and a breach.
**Outbound:** an `AdaptiveExecutionAssessment` — confidence, plan, executed
agents, hypotheses, evidence ledger, policy decisions, readiness, and a
recommendation requiring approval.
**Persistent side effect:** optional outcome feedback and learned patterns
written back into the fixture set, which changes future runs.

---

## 3 · Layer model

Four layers. Each answers exactly one question and is not permitted to answer
another's. This boundary was not present originally; it was imposed after five
faults of one shape were found (§11.1) and is now enforced by tests.

| # | Layer | Module | Question it owns |
|---|---|---|---|
| 1 | Semantic graph | `graph_engine.py` | What exists, what depends on what, what a pattern is declared to cover |
| 2 | Experience ledger | `experience_ledger.py` | What has happened, and what each case is worth |
| 3 | Confidence engine | `operational_confidence_engine.py` | How alike is this case, how reliable is that pattern, what plan is warranted |
| 4 | Evidence fusion | `evidence_fusion_agent.py` | What to tell a human, and how to weigh sources against one another |

### 3.1 The authority rule

> The confidence engine owns operational judgement.
> Evidence fusion owns explanation and adjudication between sources.

Consequences, each enforced by a test in `test_layer_agreement.py`:

- A judgement made in layer 3 is **passed** to layer 4, never re-derived
  there. `EvidenceFusionAgent.analyze()` takes `reconsult_documentation` as a
  keyword argument rather than computing it.
- Layers 3 and 4 read experience **only** through layer 2. Neither opens
  `outcome_history.json` directly.
- Both must select the same pattern, count the same cases, and compute the
  same weighted success rate for any scenario.

### 3.2 Supporting components

| Module | Role |
|---|---|
| `adaptive_execution_orchestrator.py` | Sequences the run: assess → plan → execute → reassess → re-plan → recommend |
| `adaptive_planner.py` | Selects an orchestration mode from confidence, drift, coverage and flags |
| `skill_resolver.py` | Maps required skills to registered agents |
| `policy_layer.py` | PDP/PEP for agent-to-agent, tool and data access |
| `runtime_confidence_reassessment.py` | Applies runtime signals as penalties and capped credits |
| `automation_readiness.py` | Advisory readiness verdict; never authorises action |
| `case_fingerprint.py`, `case_similarity.py` | Presentation-based recall |
| `documented_reasoning.py` | Reasoning from written procedure when experience is absent |
| `pattern_learning.py`, `outcome_feedback.py` | The learning loop write path |
| `threshold_explorer.py` | Re-plans every scenario against altered thresholds (demo control) |

**Skill agents:** `graph_context_agent`, `telemetry_agent`,
`knowledge_retrieval_agent`, `vendor_health_agent`, and the three in
`skill_agents.py` (due diligence, change/dependency, recommendation).

---

## 4 · Data model

Sixteen synthetic fixture files under `json/`. The engine is generic over
them: adding a known error, an outcome, a relationship or a scenario changes
behaviour with no code change.

### 4.1 Core entities

| File | n | Purpose |
|---|---|---|
| `entities.json` | 30 | Services, components, capabilities. Carries `entity_type`, `service_provider_type` (INTERNAL / EXTERNAL_VENDOR), `trust_level` |
| `semantic_relationships.json` | 46 | Typed edges: `DEPENDS_ON`, `ROUTED_THROUGH`, `SUPPORTS`, `APPLIES_TO`, `MODIFIES`. Each carries `relationship_authority` and `confidence` |
| `known_errors.json` | 9 | Curated patterns: `applies_to_entity_id`, `symptom_category`, `trigger_metric_id`, `knowledge_status`, `trust_level`, validity window |
| `outcome_history.json` | 118 | The experience base — see §4.2 |
| `knowledge_documents.json` | 20 | KB / RUNBOOK / PIR / WIKI with `trust_level`, `symptom_categories`, `entity_ids`, `last_validated_at` |
| `scenarios.json` | 9 | Demonstration entry points. **Expected-result fields are deliberately ignored by the engine** |
| `telemetry_samples.json` | 456 | Metric time series per scenario |
| `health_observations.json` | 18 | The trigger records |
| `changes.json`, `incidents.json`, `problems.json`, `vendor_advisories.json`, `business_context.json`, `metric_definitions.json`, `runtime_evidence_events.json` | — | Supporting evidence |

### 4.2 The outcome record

The single most important structure. Every field is read:

```
outcome_id, known_error_id, scenario_pattern, entity_id,
recommendation, approval_decision, human_modification,
action_performed, outcome, recovery_minutes,
recurrence_within_24h, prior_confidence,
evidence_usefulness_score, recorded_at, data_classification
```

Optional, present on peer-established records:

```
established_by_agent, established_for_domain
```

`provenance` is **not** a stored field. It is derived at read time
(`ExperienceLedger.provenance_of`) so historic records gain classification
without migration:

| Condition | Class |
|---|---|
| `established_by_agent` present | `PEER_AGENT` |
| `approval_decision` in {rejected, declined} | `HUMAN_VERIFIED` |
| `human_modification` not in {"", "None"} | `HUMAN_VERIFIED` |
| otherwise | `SELF_OUTCOME` |

An unamended approval is **not** verification. That distinction is why 22
recorded human modifications and 108 approvals stopped being inert data.

### 4.3 Runtime-written stores

| File | Written by | Effect |
|---|---|---|
| `runtime_outcome_feedback.json` | `OutcomeFeedbackStore` | Appended to outcome history by the ledger |
| `learned_patterns.json` | `PatternLearner` | Loaded alongside known errors; becomes a graph node |
| `refutation_ledger.json` | `PatternLearner` | Attenuates documents *and* the patterns learned from them |

---

## 5 · Control flow

`AdaptiveExecutionOrchestrator.execute(correlation_id, scenario_id)`:

1. **Assess** — `confidence_engine.assess(scenario_id)` produces the initial
   `OperationalConfidenceAssessment`.
2. **Plan** — `planner.plan()` selects an orchestration mode. Plan widths are
   recorded in order so a peak excursion stays visible even if the plan
   returns to its starting width.
3. **Resolve** — `skill_resolver` maps required skills to registered agents.
   Unregistered agents are refused at the PEP.
4. **Execute** — each skill runs through three enforcement points:
   - `a2a_pep` — may this agent be invoked for this skill
   - `mcp_pep` — may it use this tool in this mode
   - `data_pep` — may it read this data domain
5. **Discover** — skills may surface runtime evidence signals
   (`RuntimeEvidenceProbe`). These are gathered from *all* skills completed
   since the last reassessment, not only the one carrying the hook.
6. **Reassess** — `RuntimeConfidenceReassessor` applies penalties in full and
   credits capped, subject to the credit gate (§7.3).
7. **Re-plan** — if the mode changes:
   - **Expansion** preserves completed work and adds skills.
   - **Contraction** is a *substitution, not a truncation*: pending skills the
     wider plan queued are cancelled while the narrower plan introduces its
     own. Completed work is never cancelled.
8. **Recommend** — `AdaptiveRecommendationAgent` calls fusion and assembles
   the output. Creating the assessment record is a write, so the PDP returns
   `ESCALATE` with a `HUMAN_APPROVAL_BEFORE_ACTION` obligation.
9. **Readiness** — advisory only, computed after the fact.

### 5.1 Recall path

```
observation
   │
   ├─▶ CaseFingerprinter.for_observation()        what this case looks like
   │
   ├─▶ ExperienceLedger.admissible(patterns)      what may be recalled at all
   │
   ├─▶ CaseSimilarity.compare() per pattern       how alike, graded
   │
   ├─ score ≥ 0.35 ─▶ candidates ──▶ _assess_candidate() per candidate
   │
   └─ nothing ──▶ DocumentationReasoner.propose() ──▶ documented assessment
                        │
                        └─ nothing ──▶ governed non-diagnosis
```

If a candidate *is* found but scores below the documentation ceiling (0.45),
documentation is consulted **as well** and carried as alternatives (§8.4).

---

## 6 · The confidence model

### 6.1 Factor score

Five weighted factors, from `config/confidence_policy.json`:

| Factor | Weight | Source |
|---|---|---|
| `outcome_reliability` | 0.35 | Weighted success, recurrence, usefulness and sample maturity |
| `graph_applicability` | 0.20 | The similarity score for this pattern |
| `evidence_coverage` | 0.20 | Breaching metrics accounted for by the pattern |
| `knowledge_readiness` | 0.15 | Governed knowledge present and not stale (180 days) |
| `trigger_support` | 0.10 | Trigger metric matches the pattern's declared metric |

`raw = Σ(factor × weight)`, then `score = clamp(raw − Σpenalties, 0, 1)`.

### 6.2 Penalties

| Penalty | Value | Raised when |
|---|---|---|
| `recent_high_risk_change` | 0.15 | High-risk change on the entity within 6h |
| `recent_failure_signal_HIGH` | 0.15 | Pattern's recent failure signal is HIGH |
| `eroding_confidence` | 0.10 | Drift status ERODING |
| `stale_or_missing_governed_knowledge` | 0.10 | No governed knowledge |
| `insufficient_outcome_sample` | 0.08 | Fewer than 15 recorded cases |
| `frequently_amended_by_humans` | ≤0.18 | Amendment rate above 0.25, **ramped** |
| `previously_rejected_by_approver` | ≤0.25 | Scaled by rejection rate |
| `provisional_pattern` | 0.22 | Learned pattern not yet established |
| `remedy_previously_ineffective` | 0.30 | Applied here, zero weighted success |
| `account_previously_rejected` | ≤0.30 | Human rejected this account for this entity |
| `candidate_ambiguity` | ≤0.30 | Multiple close candidates |

**Two deliberate non-additivities:**

- `provisional_pattern` and `insufficient_outcome_sample` are charged **once,
  at the larger**. They describe one fact — the pattern is new — and stacking
  them made the system less confident after learning something than it had
  been reading a manual.
- The supervision penalty **ramps** from a floor of 0.25 to saturation at
  0.60 rather than stepping. A case at 0.249 and one at 0.251 differing by the
  whole penalty is not supportable by any operational reading.

### 6.3 Weighting of a recorded case

Applied once, in the ledger:

```
weight = 0.5^(age_days / 90) × provenance_weight(row)
```

`provenance_weight` is:

| Class | Base | Then |
|---|---|---|
| `HUMAN_VERIFIED` | 1.2 | — |
| `SELF_OUTCOME` | 1.0 | — |
| `PEER_AGENT` | 0.8 | × reliability, capped at 0.9; × 0.1 if the agent lacks standing over the asserted domain |

**Standing is not reliability.** The telemetry agent (0.96 reliable) weighs
0.08 on a vendor advisory; the vendor agent (0.92) weighs 0.736 — because the
claim is the vendor agent's to make.

### 6.4 Asymmetry

Penalties apply in full and immediately. Credits are capped at 0.10 per
reassessment, cannot lift runtime confidence above 0.95, and are withheld
entirely while any unresolved *resolvable* hard flag remains.

The purpose is to make confidence unmanufacturable: an agent cannot cycle
evidence to raise its own certainty.

### 6.5 Bands

`HIGH ≥ 0.85`, `MEDIUM ≥ 0.50`, `LOW` otherwise. Bands gate plan eligibility;
they do **not** gate governance (§7).

---

## 7 · Governance model

### 7.1 Three flag tiers

Every flag is placed in exactly one tier, deliberately. `test_architecture_
invariants.py` asserts the placement.

**Tier 1 — bars the narrow plan** (`orchestration_policies.json`,
`ACCELERATED_VALIDATION.entry_conditions.disallowed_hard_flags`):
`RECENT_HIGH_RISK_CHANGE`, `MISSING_GOVERNED_KNOWLEDGE`,
`INSUFFICIENT_OUTCOME_HISTORY`, `NO_APPLICABLE_KNOWN_ERROR`,
`VENDOR_STATUS_UNKNOWN`, `EXPERIENCE_TRANSFERRED_NOT_DIRECT`,
`PATTERN_PROVISIONAL_NOT_ESTABLISHED`, `REMEDY_PREVIOUSLY_INEFFECTIVE`,
`HYPOTHESIS_FROM_DOCUMENTATION_ONLY`, `PATTERN_ACCOUNT_PREVIOUSLY_REJECTED`

**Tier 2 — suspends automation readiness**
(`automation_readiness_policy.suspension_hard_flags`): the tier-1 governance
flags plus `CREDIBLE_KNOWLEDGE_CONTRADICTION`, `KNOWLEDGE_VALIDATION_FAILED`,
`OBSERVABILITY_COVERAGE_LOW`, `NO_RECORDED_EXPERIENCE`,
`EXPERIENCE_HELD_ONLY_BY_PEER_AGENT`.

Principle: **anything not backed by the system's own recorded outcomes cannot
be automated.** Documentation, analogy and peer findings are all legitimate
bases for a proposal and none is evidence the action works here.

**Tier 3 — informational**: `WEAK_PATTERN_DOCUMENTATION_RECONSULTED`,
`NEWER_DOCUMENTATION_AVAILABLE`. These disclose and carry no plan effect.

### 7.2 Thresholds do not gate governance

Lowering the HIGH band from 0.85 to 0.30 re-plans **nothing**, because tier-1
flags are categorical. This is asserted in `test_threshold_explorer.py` and
demonstrable live in the *Confidence controls* tab.

Confidence decides how much investigation is proportionate. It does not decide
whether governance applies.

### 7.3 Standing flags and the credit gate

Some flags describe the **evidence base** rather than the run and can never be
resolved by a runtime signal. Gating credit on those would withhold it
permanently rather than pending an answer, so they are exempted
(`runtime_signal_policy.limits.standing_flags_exempt_from_credit_gate`). They
still bar the narrow plan and still suspend automation.

### 7.4 PDP/PEP

`policy_layer.py` implements a decision point and three enforcement points.
Decisions: `ALLOW`, `ALLOW_WITH_OBLIGATIONS`, `ESCALATE`, `DENY`.

Enforced independently of agent design. The vendor health agent asks for both
vendor advisories and telemetry; it is registered only for the former, and the
second request is refused. The boundary the agent was designed to respect is
also enforced from outside it.

---

## 8 · Recall and reasoning

### 8.1 Case fingerprint

Describes a case by presentation rather than label: `entity_id`,
`entity_type`, `service_provider_type`, `depends_on`, `depended_on_by`,
`parent_services`, `breaching_metrics`, `symptom_categories`, `severity_band`,
`impacted_capabilities`, `blast_radius`, `declared_patterns`,
`covered_entities`.

### 8.2 Similarity

Seven weighted dimensions (`similarity_policy.json`):

| Dimension | Weight |
|---|---|
| `declared_applicability` | 0.28 |
| `symptom_overlap` | 0.26 |
| `same_entity` | 0.18 |
| `structural_position` | 0.14 |
| `entity_kind` | 0.06 |
| `capability_overlap` | 0.05 |
| `severity_band` | 0.03 |

Two design choices that were arrived at by failure:

- **Presentation outweighs location.** An earlier weighting put `same_entity`
  above `symptom_overlap` and ranked "familiar component, unseen symptom"
  above "sibling component, same symptom" — the anchoring bias the model
  exists to remove.
- **`declared_applicability` is gated by symptom.** A curated `APPLIES_TO`
  edge is strong evidence, but a declaration is about a *pattern*, and a
  pattern includes how it presents. Pure similarity without it discarded
  curated knowledge; ungated, it reintroduced anchoring.

Symptom coverage uses **asymmetric containment**, not Jaccard: what matters is
whether the pattern covers the presenting symptom, not whether vocabularies
match. Symmetric overlap penalises exactly the well-documented patterns that
are most useful.

`DIRECT` requires same entity **and** full symptom coverage. Everything else
is `TRANSFERRED` and capped at 0.85.

### 8.3 Documented reasoning

When nothing is recalled, `DocumentationReasoner` proposes from written
procedure. Eligibility: published, content-safe, entity-matched, symptom
coverage ≥ 0.5, and **published on or before the assessment time** — without
that last check an August post-incident review would inform a July case.

Support is scored on symptom coverage (0.40), document trust (0.30), document
type (0.18) and freshness (0.12), then **scaled** into the permitted band
rather than clipped at it — clipping would give a current trusted runbook and
a lapsed wiki page identical confidence the moment both cleared the ceiling.

Ceiling 0.45, deliberately below the MEDIUM band so a documented proposal
cannot be mistaken for a validated one at a glance.

### 8.4 Reconsultation

A recalled pattern scoring below 0.45 does **not** end the search. Thin
experience is exactly where the written record is most likely to know
something the system does not — including material published since the pattern
was last applied, which raises `NEWER_DOCUMENTATION_AVAILABLE` and is named in
the recommendation.

Documented alternatives are appended **after** the leader is chosen and never
sorted into contention with it: a documented score and an experience score are
not the same measurement.

### 8.5 Governed non-diagnosis

When neither experience nor documentation applies, the run completes with
`hypothesis_id = NO_GOVERNED_PATTERN`, confidence 0.000, an investigative
recommendation, and an explicit refusal to borrow a remedy from an unrelated
pattern. Validation steps include recording the eventual resolution, so the
unexplained case can become experience.

---

## 9 · The learning loop

```
 unseen ──▶ documented proposal ──▶ human validation ──▶ pattern minted
   0.450        names its source        CONFIRMED /          Provisional,
                                        CORRECTED /          1 case
                                        REJECTED
                                             │
                                             ▼
                                    outcome recorded
                                             │
                    ┌────────────────────────┴──────────────────┐
                    ▼                                           ▼
            remedy worked                              remedy failed
            0.341, recalls its own pattern      ~0.02, REMEDY_PREVIOUSLY_
            climbs with each case               INEFFECTIVE raised
                    │
                    ▼
            15 cases at ≥0.8 success ──▶ promoted, provisional penalty drops
```

### 9.1 Design constraints

- **A learned pattern is written as an ordinary known error.** One requiring a
  special lookup would not have been learned. It also becomes a graph node, so
  an expert can later declare it applicable to a component — not because it
  has earned the declaration, but so that it *can*.
- **Outcomes attach to the pattern, not the document that proposed it.**
  `feedback_from_assessment(..., known_error_id=...)` exists for exactly this;
  without it the new pattern accumulates no cases.
- **Rejection is evidence, not a ban.** Support decays 0.30 per rejection with
  a floor of 0.15. A refuted account stays offerable when nothing better
  explains the presentation, with the prior rejection and the rejector named.
  A human can reject wrongly, and a system that treats one rejection as final
  makes that error unfalsifiable.
- **Promotion is computed at read time**, so a falling success rate demotes
  without anything having to remember to.
- **Sufficiency is defined once.** Promotion reads
  `confidence_policy.thresholds.minimum_outcome_sample`; it does not carry its
  own number. Two numbers that must agree will eventually stop agreeing.

---

## 10 · Policy surfaces

Every operational judgement lives in `config/`, not in code.

| File | Governs |
|---|---|
| `confidence_policy.json` | Bands, factor weights, penalties, thresholds, recency half-life |
| `experience_trust_policy.json` | Provenance weights, standing, attenuation, supervision, pattern maturity and promotion |
| `similarity_policy.json` | Dimension weights, similarity floor, transfer ceiling |
| `documentation_policy.json` | Eligibility, support weights, freshness decay, ceiling, refutation decay, reconsultation threshold |
| `orchestration_policies.json` | Modes, entry conditions, required skills, disallowed flags |
| `runtime_signal_policy.json` | Signal penalties and credits, credit gate, standing-flag exemptions |
| `automation_readiness_policy.json` | Thresholds, suspension flags, control profiles |
| `access_policies.json`, `agent_registry.json`, `skill_catalog.json` | PDP rules, agent standing and data domains, skill definitions |
| `vendor_health_policy.json` | Freshness, trusted authorities, status vocabulary |
| `servicenow_field_mapping.json` | Conceptual-to-field mapping for the ServiceNow boundary |

**Single-interpreter rule.** A policy read by more than one production module
must be declared, with a reason, in `test_architecture_invariants.py`. Reading
a policy to *display* it is not interpreting it; reading it to *decide* is,
and that happens in one place.

---

## 11 · Design decisions and their rationale

### 11.1 Layer divergence — the fault class that shaped the architecture

Five faults of one shape were found across two sprints: two components
independently deriving the same judgement, on different data or different
scales, and reaching different answers. Each was internally correct, so no
behavioural test caught any of them.

| Fault | Effect |
|---|---|
| Fusion never read `runtime_outcome_feedback.json` | Everything learned at runtime was visible to the planner and invisible to the explainer |
| Fusion's outcome lookup required `scenario_pattern` to match | Redundant on shipped fixtures, silently wrong for runtime records |
| Fusion counted outcomes raw; the engine weighted them | 0.55 against 0.47 over the same twenty cases — the number a human read was not the number that chose the plan |
| Pattern admissibility decided in both modules | A learned pattern was recallable by the planner and invisible to the explainer |
| Both layers judged "thin recall" on their own scales | A plan chosen on one premise, served by a stage acting on another |

**Resolution:** one owner per judgement (§3.1), plus `test_layer_agreement.py`
(11 tests) and `test_architecture_invariants.py` (11 static guards). Each
guard was verified by injecting the original fault and confirming it fires.

### 11.2 Why similarity is graded, not boolean

Applicability was once "does an `APPLIES_TO` edge reach this entity" — a
question about filing, not resemblance. It answered *yes* for a familiar
component with an unfamiliar symptom and *no* for an identical symptom on a
structural sibling. Opposite failures, both wrong.

### 11.3 Why admissibility and worth are separate questions

The retrieval filter once admitted only `Active`/`Trusted` patterns. A learned
pattern is `Provisional` by construction, so it could be recorded and never
recalled — inert, which is not learning. Provisional patterns are now admitted
and then discounted.

### 11.4 Why documentation never narrows a plan

Trust in a document is trust in its author. It is not evidence that the
procedure works on this system, and only an outcome can supply that.

### 11.5 Why the plan contracts by substitution

Truncating a plan would cancel completed work and lose evidence already
gathered. Contraction cancels only *pending* skills while the narrower plan
introduces its own, and plan width is reported separately from agent
participation so a narrowing plan never appears to contradict the agents that
informed it.

### 11.6 Why the failed remedy is a named fact

A failed remedy expressed only as a lower success rate is indistinguishable
from thin evidence. Carrying `REMEDY_PREVIOUSLY_INEFFECTIVE` forward is what
stops the second encounter repeating the first.

---

## 12 · Test architecture

468 tests. Four suites carry architectural weight:

| Suite | Asserts |
|---|---|
| `test_story_shape.py` (23) | Directions and orderings, never fixture values. A test pinning 0.974 breaks when the data improves; these assert that a contradiction *lowers* confidence |
| `test_layer_agreement.py` (11) | The two layers select the same pattern, count the same cases, weight them identically, admit the same patterns |
| `test_architecture_invariants.py` (11) | No shared fact read by one layer only; no policy with an undeclared second interpreter; no judgement made twice |
| `test_demo_narrative.py` (21) | The app cannot caption a scenario with a claim its own run contradicts; quoted figures match the data |

`test_app_integrity.py` performs static AST checks on the Streamlit layer,
which no other test executes — a function deleted by a careless edit otherwise
stays green through the whole suite and fails in front of an audience. Two
panels were once deleted by a slice replacement and shipped broken for four
commits before this existed.

### 12.1 Regression baseline

Any change must reproduce these or explain the difference:

| Scenario | Confidence | Plan |
|---|---|---|
| `SCN-PAY-001` | 0.974 → 0.974 | Accelerated, 3 agents |
| `SCN-QUEUE-001` | 0.313 → 0.313 | Full, 5 agents |
| `SCN-PAY-CONTRADICT-001` | 0.974 → 0.754 | Accelerated → Full |
| `SCN-PAY-RESOLVED-001` | 0.974 → 0.854 | Accelerated |
| `SCN-CROSS-GATEWAY-001` | 0.765 → 0.865 | Full → Accelerated |
| `SCN-PAY-EU-001` | 0.872 → 0.872 | Full (transferred) |

---

## 13 · Extension points

| To add… | Do this | Code change? |
|---|---|---|
| A scenario | Add to `scenarios.json` + an observation + telemetry samples | No |
| A known pattern | Add to `known_errors.json`; optionally an `APPLIES_TO` edge | No |
| Experience | Append to `outcome_history.json` or write runtime feedback | No |
| A dependency | Add to `semantic_relationships.json` with an authority | No |
| A knowledge document | Add to `knowledge_documents.json` | No |
| An orchestration mode | Add to `orchestration_policies.modes` with entry conditions | No |
| A skill | `skill_catalog.json` + an agent in `agent_registry.json` | Agent implementation |
| A confidence factor | Weight in `confidence_policy.weights` | Factor computation |

**Scenario files carry `expected_confidence`, `expected_strategy` and
`expected_safety_status`. The engine ignores all three.** They exist as
documentation of intent, and the engine deriving its own answer is what makes
the demonstration meaningful.

---

## 14 · Known limitations and deferred work

| Item | Status |
|---|---|
| **Live ServiceNow sync** | Built (`servicenow_sync.py`, `servicenow_table_client.py`) and deliberately not on the demo path. Requires PDI credentials |
| **Retrieval breadth** | `knowledge_retrieval_agent` uses lexical relevance and can surface material about other components. Resolved by labelling and weighting rather than gating (§8.4) — the ledger shows lexical-only items at reduced reliability contributing nothing |
| **Human validation UI** | Validation is exercised through `PatternLearner` and the Learning loop tab, not through a ServiceNow form |
| **Peer agent ecosystem** | One peer-established pattern (`KE-VENDOR-SAAS-001`, 10 records). The weighting generalises; the fixture set does not yet exercise many peers |
| **Confidence controls scope** | The slider varies bands only. Factor weights and penalties are not exposed, deliberately — they are the model, not a setting |
| **Single-tenant fixtures** | No multi-tenant or per-business-unit policy scoping |

---

## 15 · Operating the demonstration

```bash
python rehearse.py                            # pre-demo gate; non-zero exit if not ready
python -m streamlit run eaios_story_app.py    # the demonstration
python demo_learning_loop.py                  # the learning arc, console
python build_deck.py                          # rebuild the deck from current data
powershell -File ./validate.ps1               # full suite + story artefacts
```

`rehearse.py` re-runs the whole arc, prints every number that will be on
screen, and fails on a stale bundle, a missing dependency, a claim the run
contradicts, approval no longer being required, or the two learning-loop
branches ceasing to differ.
