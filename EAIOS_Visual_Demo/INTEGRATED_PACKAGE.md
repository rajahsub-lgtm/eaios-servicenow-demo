# EAIOS × ServiceNow — integrated architecture package

**Implemented, designed, and proposed — with the boundary between them stated**

Rajah Subramanian · Solution Architect, AI & Data
Companion to the final interview review guide · working system at 468 passing tests

---

## 0 · How to use this

The interview guide gives you the *positioning*. `DESIGN.md` gives the
*implementation*. This document joins them, and its organising principle is
the guide's own strongest instruction:

> *"Be explicit about hands-on boundaries. Do not claim configuration of
> licensed products you could not access."*

Every architectural concept below carries a status:

| Status | Meaning |
|---|---|
| **BUILT** | Running code in the demonstration, with named evidence. You can show it |
| **DESIGNED** | Specified in the EAIOS architecture and reasoned through, not built here |
| **PROPOSED** | What you would implement for a customer, on ServiceNow platform capability |

A panel will probe the seam between these three. Stating it first converts
your biggest exposure into your most credible moment — and the honest answer
is unusually strong, because the *governance* concepts are the ones that are
built, and the unbuilt ones are mostly licensed platform features nobody
expects you to have configured.

**The sentence that does the most work:**

> "The governance mechanics are built and tested — confidence derivation,
> adaptive planning, policy enforcement, evidence fusion, outcome learning.
> What is designed rather than built is the platform substrate: RDF/SPARQL,
> zero-copy WDF, and signed delegation. I could not license those on a PDI, so
> I built native analogues and can show you exactly where the analogue ends."

---

## 1 · The evidence ladder

What you can actually put on screen, in descending order of strength.

| # | Claim | Status | Evidence you can show |
|---|---|---|---|
| 1 | Confidence is derived, not self-reported | **BUILT** | 118 outcome records, weighted by recency + provenance + standing; `0.974` vs `0.313` from the same engine |
| 2 | The plan is a consequence of confidence | **BUILT** | 3 agents at 0.974, 5–6 below; live threshold slider re-plans in real time |
| 3 | Plans expand *and* contract mid-run | **BUILT** | `0.974 → 0.754` expands 3→6 agents; `0.754 → 0.854` contracts and cancels queued work |
| 4 | Confidence is asymmetric | **BUILT** | Penalty ≤0.22 in full; credit ≤0.10 capped, ceiling 0.95. Recovery reaches 0.854, never 0.974 |
| 5 | Cross-source context resolves one cause | **BUILT** | GitHub + Teams → shared gateway, discovered by traversal over authoritative edges |
| 6 | Policy decisions are enforced, not advisory | **BUILT** | PDP/PEP, default **DENY**, `ALLOW_WITH_OBLIGATIONS` / `ESCALATE` / `DENY`; A2A, MCP and data domains each gated |
| 7 | Governance is categorical, not a threshold | **BUILT** | Drop the HIGH band 0.85→0.30: **nothing** accelerates. Ten flags bar the narrow plan regardless |
| 8 | Evidence carries provenance and weight | **BUILT** | Contribution ledger: each source labelled with class, role, reliability, contribution and admission basis |
| 9 | Recurrence is recognised without blind reuse | **BUILT** | Case fingerprints + graded similarity; `DIRECT` / `TRANSFERRED` / `DOCUMENTED` classes |
| 10 | The system learns from validated outcomes | **BUILT** | Human validation mints a pattern; second encounter differs by what happened (`0.341` vs `~0.02`) |
| 11 | Trust attenuates and never amplifies | **BUILT** | Peer weight ≤0.9 × reliability; ×0.1 outside standing. Telemetry agent (0.96 reliable) → 0.08 on a vendor claim |
| 12 | Canonical semantic model over RDF | **DESIGNED** | Typed graph with authority and confidence on every edge — the *shape* is built, the RDF serialisation is not |
| 13 | SPARQL multi-hop discovery | **DESIGNED** | Traversal is implemented in Python over a typed graph; the query language is not |
| 14 | Zero-copy WDF retrieval | **DESIGNED** | Fixtures stand in for source adapters. The evidence contract and provenance model are built |
| 15 | OWL/SHACL design-time semantics | **DESIGNED** | Validation exists as tests and policy, not as shapes |
| 16 | Signed attenuated delegation (GOV-021) | **DESIGNED** | PDP/PEP is built; signed tokens, trust ceilings, delegation budget and expiry are not |
| 17 | Phased customer rollout | **PROPOSED** | §9 roadmap, anchored to what phase 1–2 already look like in the demo |

**Say it as:** "Rows one to eleven I can run for you now. Twelve to sixteen are
designed and I can explain the mechanism precisely — what I could not do was
license the platform features on a personal instance."

---

## 2 · AI Control Tower × EAIOS, with evidence

The five-pillar convergence from the guide, annotated with what is
demonstrable.

| Pillar | EAIOS equivalent | Status | What you can show |
|---|---|---|---|
| **Discover** | Outcome → capability → skill → agent/tool registry | **BUILT** | `skill_catalog.json`, `agent_registry.json` with skills, data domains, MCP tools, A2A protocol, reliability |
| **Observe** | Execution trace, evidence lineage, confidence movement, reasoning change | **BUILT** | Full execution trace, confidence series, plan transitions, policy decision log per run |
| **Govern** | Action taxonomy, prohibited outcomes, policy gates, approval matrix, fail-closed | **BUILT** | Default-DENY PDP, three flag tiers, mandatory approval on every path, assessment creation escalates |
| **Secure** | Agent identity, bounded delegation, source/tool authorisation, trust ceilings | **PARTIAL** | Identity, data-domain and tool authorisation **built**; signed delegation and cryptographic attenuation **designed** |
| **Measure** | Outcomes, learning, retrieval budget, review effectiveness | **PARTIAL** | Outcome capture, drift, supervision rate and calibration **built**; token/retrieval cost accounting **designed** |

**Positioning line, unchanged from the guide and now evidenced:**

> "AI Control Tower governs the enterprise AI estate. EAIOS provides a detailed
> operating model for how capabilities, skills, agents, evidence, authority and
> outcomes behave inside that governed estate — and I have a working
> implementation of the operating model's reasoning and governance core."

---

## 3 · The reference architecture

### 3.1 Built: four layers with one direction of authority

| Layer | Module | Owns |
|---|---|---|
| Semantic graph | `graph_engine.py` | What exists, what depends on what, what a pattern covers |
| Experience ledger | `experience_ledger.py` | What has happened and what each case is worth |
| Confidence engine | `operational_confidence_engine.py` | Similarity, reliability, and what plan is warranted |
| Evidence fusion | `evidence_fusion_agent.py` | Explanation and adjudication between sources |

**The rule:** the confidence engine owns operational judgement; fusion owns
explanation. A judgement is *passed*, never re-derived.

**Why this is worth mentioning to a panel:** the rule was not designed up
front. Five faults were found where two components independently derived the
same judgement and disagreed — for example, fusion reported a 0.55 success
rate on the same twenty cases the engine scored at 0.47, so the number a human
read was not the number that chose the plan. Each was internally correct;
none was caught by behavioural tests. The boundary is now enforced by eleven
agreement tests and eleven static guards, and each guard was verified by
re-injecting the original fault.

That is a *transformation* story, not a feature story, and it answers "how do
you know your architecture holds" with something better than assertion.

### 3.2 Control plane vs runtime plane

| Control plane | Status | Runtime plane | Status |
|---|---|---|---|
| Asset discovery and registration | **BUILT** | Goal execution and agent selection | **BUILT** |
| Owners, risk classes, lifecycle | **BUILT** | Evidence retrieval and fusion | **BUILT** |
| Policies, action tiers, approval rules | **BUILT** | PDP decision and PEP enforcement | **BUILT** |
| Identity and entitlement intelligence | **DESIGNED** | Signed delegation, MCP/A2A checks | **PARTIAL** — checks built, signing designed |
| Metrics, cost, outcome definitions | **PARTIAL** | Trace, confidence movement, result capture | **BUILT** |

---

## 4 · Knowledge graph and data fabric

### 4.1 What is built

A typed property graph over 30 entities and 46 relationships. Every edge
carries `predicate`, `relationship_authority`, `confidence`, `direction` and
`provenance`. Traversal is filtered to authoritative edges, so an inferred or
low-confidence relationship cannot manufacture a connection.

**The demonstrable case:** two unrelated-looking incidents — developers cannot
clone from GitHub, Teams meetings dropping — converge on one component three
hops away.

```
GitHub Enterprise ──depends on──▶ Repo access ──routed through──┐
                                                                 ├──▶ Secure web gateway ──depends on──▶ TLS policy
Microsoft Teams  ──depends on──▶ Signalling  ──routed through──┘                                         (changed 6h before)
```

Nothing in either incident declares the relationship. Remove the edge and the
discovery does not happen.

### 4.2 What is designed, not built

| Concept | Designed as | Honest statement |
|---|---|---|
| RDF canonical model | Named graphs, canonical identity, source semantic projection | "The graph shape, edge semantics, authority and provenance are built. The RDF serialisation and triple store are not" |
| SPARQL discovery | Multi-hop path queries returning authoritative records | "Traversal is implemented directly. SPARQL would replace the traversal implementation, not the model" |
| Zero-copy / WDF | Source adapters returning filtered current evidence | "Fixtures stand in for adapters. What is built is the evidence contract — typed, provenanced, timestamped, with source locators" |
| PROV-O lineage | Formal provenance vocabulary | "Provenance is carried on every contribution; it is not expressed in PROV-O" |

**The zero-copy answer stays exactly as the guide has it** — the source remains
authoritative, filtered bytes still move, semantic pointers and governance
metadata persist, retrieval is bounded by purpose and policy, and raw results
are discarded after use. That answer is unaffected by what is built, because
it is a statement about the pattern.

---

## 5 · Governance

### 5.1 Built: three flag tiers

Every flag is placed in exactly one tier, deliberately, and a static test
asserts the placement.

| Tier | Effect | Members |
|---|---|---|
| **Bars the narrow plan** | Forces full investigation | Recent high-risk change · missing governed knowledge · insufficient outcome history · no applicable pattern · vendor status unknown · transferred experience · provisional pattern · previously ineffective remedy · documentation-only hypothesis · previously rejected account |
| **Suspends automation** | Readiness cannot reach CANDIDATE | The above, plus credible knowledge contradiction, knowledge validation failure, low observability coverage, no recorded experience, experience held only by a peer agent |
| **Informational** | Discloses, no plan effect | Reopened knowledge search · newer documentation available |

**The principle behind tier 2:** anything not backed by the system's own
recorded outcomes cannot be automated. Documentation, analogy and a peer
agent's finding are all legitimate bases for a *proposal*, and none is
evidence that the action works here.

### 5.2 Built: policy enforcement

`policy_layer.py` — a decision point and three enforcement points, default
**DENY**, decisions `ALLOW_WITH_OBLIGATIONS` / `ESCALATE` / `DENY`.

Enforced independently of agent design. The vendor health agent requests both
vendor advisories and telemetry; it is registered only for the former and the
second request is refused. **The boundary the agent was designed to respect is
also enforced from outside it** — that distinction is the whole point of a PEP
and it is worth saying explicitly.

Creating an assessment record is a write, so the PDP returns `ESCALATE` with a
`HUMAN_APPROVAL_BEFORE_ACTION` obligation. No path in the system reaches an
action without a human.

### 5.3 The demonstration that lands hardest

Lower the HIGH confidence band from 0.85 to 0.30 — a more than 60% reduction
in the bar — and **nothing accelerates**. Four scenarios clear the band
comfortably and every one still runs the full investigation.

> "Confidence decides how much investigation is proportionate. It does not
> decide whether governance applies. That is the difference between a
> threshold and a control."

### 5.4 Designed, not built

| Concept | Position |
|---|---|
| OWL/SHACL | "OWL defines meaning, SHACL validates conformance at ingestion and nearline. Approved semantics compile into versioned registries, policy tables and eligibility rules; the hot path runs deterministic checks. In the demo, the compiled artefacts exist as policy files — the design-time layer that would generate them does not" |
| GOV-021 signed delegation | "PDP/PEP is built. Signed time-bound tokens carrying root goal, trust ceiling, delegation budget, caller chain and expiry — where each step may only attenuate — are designed. The Veza comparison stands: access intelligence answers *who has effective access*; attenuated delegation answers *how much authority may be passed on during one execution*" |
| Kill switch / delegation budget | Designed. The demo's equivalent is categorical flags and mandatory approval |

---

## 6 · Operational confidence — the mechanism

Fully built, and the strongest single answer to *"why not let the model decide
confidence?"*

### 6.1 Factors

| Factor | Weight | Source |
|---|---|---|
| `outcome_reliability` | 0.35 | Weighted success, recurrence, usefulness, sample maturity |
| `graph_applicability` | 0.20 | Graded similarity for this pattern |
| `evidence_coverage` | 0.20 | Breaching metrics accounted for |
| `knowledge_readiness` | 0.15 | Governed knowledge present and not stale (180 days) |
| `trigger_support` | 0.10 | Trigger metric matches the pattern's declared metric |

`score = clamp(Σ(factor × weight) − Σpenalties, 0, 1)`

### 6.2 What weights a single recorded case

```
weight = 0.5^(age_days / 90) × provenance_weight
```

| Provenance | Base | Then |
|---|---|---|
| `HUMAN_VERIFIED` | 1.2 | — |
| `SELF_OUTCOME` | 1.0 | — |
| `PEER_AGENT` | 0.8 | × reliability, capped 0.9; × 0.1 if outside standing |

**Two points worth making aloud:**

*Provenance is derived, not declared.* An approval with no amendment is not
verification — it is a rubber stamp, and it is classed as a self-outcome. A
human who amended or overruled engaged with the case. That single distinction
turned 22 recorded human modifications and 108 approvals from inert fields
into signal.

*Standing is not reliability.* The telemetry agent is more reliable than the
vendor agent (0.96 vs 0.92) and weighs 0.08 against 0.736 on a vendor
advisory, because that claim is not its to make. **Authority attenuates
through delegation; trust attenuates through transfer.** Neither amplifies.

### 6.3 Asymmetry

Penalties apply in full and immediately. Credits are capped at 0.10 per
reassessment, cannot lift runtime confidence above 0.95, and are withheld
while any resolvable flag remains unresolved.

> "An agent cannot manufacture confidence by cycling evidence."

---

## 7 · Memory — pattern memory is built

Mapping the guide's memory hierarchy to what exists:

| EAIOS layer | ServiceNow anchor | Status | In the demo |
|---|---|---|---|
| Hot Semantic Context | Active incident's service graph and evidence | **BUILT** | Graph context per run, scoped to the traversal |
| **Pattern Memory** | Incident fingerprints, known-error outcomes | **BUILT** | `case_fingerprint.py` — presentation-based, not label-based. Graded similarity, `DIRECT`/`TRANSFERRED`/`DOCUMENTED` |
| Persistent Semantic Index | CMDB, Service Graph, canonical identity | **DESIGNED** | Entity registry stands in |
| Cold Authoritative Context | Discovery/ITOM history, external WDF sources | **DESIGNED** | Fixtures stand in |
| Transient Execution Context | Prompts, query results, delegation state | **BUILT** | Execution trace, discarded to governed provenance |

**Pattern memory is the one to demonstrate**, because it answers the recurrence
question concretely. Recall was once boolean graph reachability — which
answered *yes* for a familiar component showing an unfamiliar symptom and *no*
for an identical symptom on a structural sibling. Opposite failures, both
wrong. It is now graded on seven weighted dimensions, with presentation
weighted above location precisely to remove that anchoring.

**Operational Outcome Calibration** (never the old acronym): validated outcomes
recalibrate future confidence under bounded governance. Built — promotion at
15 successful cases, evaluated from the record at read time so a falling
success rate demotes without anything having to remember to.

---

## 8 · The demonstration — six beats, ten minutes

| # | Beat | What it proves | Numbers |
|---|---|---|---|
| 1 | It has seen this 49 times | Confidence is earned and buys narrowness | `0.974` → 3 agents |
| 2 | Confidence lost, then partly recovered | Asymmetry; contradiction is not promoted to truth | `0.974 → 0.754 → 0.854` |
| 3 | One cause, two platforms | Graph traversal, not declaration | `0.765 → 0.865`, full → accelerated |
| 4 | Never here, fifty times next door | Transfer is recognised *and* discounted | `0.872` HIGH — still the full plan |
| 5 | Never seen at all | Reads the runbook; then, with no runbook, says nothing | `0.450` then `0.000` |
| 6 | Seen once before | What happened last time changes what happens now | `0.341` worked vs `~0.02` failed |

Each beat raises the question the next answers. **Beat 5 is the one they will
remember** — a complete, governed output that proposes no cause at all.

**Optional seventh:** the confidence-threshold control (§5.3), for when
someone challenges whether the plan really follows the evidence.

---

## 9 · Implementation roadmap for a customer

The guide's five phases, annotated with what the demonstration already shows.

| Phase | Implement | Proof point | Demo evidence |
|---|---|---|---|
| **1 · Discover and anchor** | Inventory outcomes, capabilities, skills, agents, tools, owners, risks; connect CMDB/Service Graph | Every AI asset has purpose and ownership | **BUILT** — skill catalogue and agent registry with domains, tools, reliability |
| **2 · Ground in context** | WDF/zero-copy access, canonical semantic model, evidence contracts | Agent can explain which source records support its conclusion | **PARTIAL** — evidence contract and contribution ledger built; zero-copy adapters designed |
| **3 · Govern runtime** | AI Control Tower policies, AI Gateway/MCP governance, approvals, action tiers, audit | Unsafe or unauthorised actions fail closed | **BUILT** — default-DENY PDP, three flag tiers, mandatory approval |
| **4 · Observe and explain** | Execution trace, reasoning changes, confidence movement, policy decisions, provenance | A reviewer can reconstruct the decision path | **BUILT** — full trace, confidence series, plan transitions, evidence ledger |
| **5 · Measure and learn** | Business outcomes, cost, review effectiveness, outcome calibration, graph-health KRIs | Confidence improves under bounded governance | **PARTIAL** — outcome calibration and supervision built; cost accounting designed |

**Minimum viable 80/20:** one high-value use case, one canonical service
context, a small governed source set, explicit human approval, end-to-end
traceability, outcome capture. Do not begin by governing the entire enterprise
graph or enabling autonomous remediation.

> "That is exactly the scope of what I built — one use case, one service
> domain, a bounded source set, and no autonomy. It was a deliberate choice,
> not a limitation of effort."

---

## 10 · Questions, with evidence anchors

The guide's answers stand. These add *what you can show* when invited deeper.

| Question | Answer stays | Evidence to offer |
|---|---|---|
| **Why not let the LLM decide confidence?** | Derived from identity, evidence quality, source trust, freshness, conflicts, history and policy | Show the five factors and the provenance weighting. Show 0.974 and 0.313 from the same engine on different histories |
| **Fast Pass vs Full Investigation?** | Non-compensatory conditions; any failure expands the plan | Show the threshold slider: drop the band 60% and nothing accelerates. Ten categorical flags |
| **How do you keep a graph trustworthy?** | Edges as assertions with authority, provenance, time, confidence, lifecycle | Show the authority filter on traversal and the confidence field on every edge. Be clear SHACL is designed |
| **How does an alert become a conclusion?** | Resolve to canonical service, traverse, retrieve, fuse | Run beat 3 live — two platforms, one gateway, discovered |
| **Recurrence without blind reuse?** | Pattern memory recognises; it does not assume cause | Show `DIRECT` vs `TRANSFERRED` — 0.872 HIGH still runs the full plan |
| **How do you measure success?** | Separate observation from value measurement | Show outcome capture, drift, supervision rate and the maturity ladder to promotion |
| **What would you implement first?** | One bounded use case, small source set, one approval boundary | "This, exactly. Here it is running" |
| **Have you implemented licensed WDF/KG/ACT?** | PDI lacked licences; native analogues and external labs | §1 ladder — name rows 12–16 as designed without being asked twice |
| **Is EAIOS the same as AI Control Tower?** | Converges on the same control-plane functions; an operating architecture, not product equivalence | §2 mapping with the PARTIAL rows visible |

---

## 11 · Risk phrases and boundaries

**Do not say** → **Say instead**

- ~~"I built the same product"~~ → "It converges on the same control-plane functions. It is an operating architecture, not a claim of product equivalence."
- ~~"Yes, fully implemented"~~ → "The governance mechanics are built and tested. The platform substrate — RDF/SPARQL, zero-copy WDF, signed delegation — is designed. I can show you exactly where the analogue ends."
- ~~"The model score is enough"~~ → "Operational confidence is derived from evidence quality, source trust, freshness, conflicts and history — not self-reported certainty."
- ~~"Graphs are better databases"~~ → "Persist semantic identity and relationships; retrieve current detailed evidence from authoritative sources when required."
- ~~"We can govern everything"~~ → "Automate structural and statistical checks; route high-impact exceptions to stewards."
- ~~RLOO~~ → **Operational Outcome Calibration.**

**State the boundary before the panel discovers it.** The guide is right that
this is a risk. The integration makes it an asset: the things you *did* build
are the governance-critical ones, and that is the more impressive half.

---

## 12 · Closing

> "Customers do not need another abstract AI framework. They need a practical
> path from business outcome to trusted context, governed action and
> measurable learning. I built the reasoning and governance core of that path
> and ran it end to end — including the part where the system has no answer
> and says so. ServiceNow is exceptionally well positioned to provide the
> control plane it belongs in."

---

## Appendix A · Verification

468 tests. Four suites carry architectural weight.

| Suite | Asserts |
|---|---|
| `test_story_shape.py` (23) | Directions and orderings, never fixture values. A test pinning 0.974 breaks when data improves; these assert a contradiction *lowers* confidence |
| `test_layer_agreement.py` (11) | The two layers select the same pattern, count the same cases, weight them identically |
| `test_architecture_invariants.py` (11) | No shared fact read by one layer only; no policy with an undeclared second interpreter; no judgement made twice |
| `test_demo_narrative.py` (21) | The app cannot caption a scenario with a claim its own run contradicts |

Each structural guard was verified by injecting the original fault and
confirming it fires. **A guard nobody has seen fail is not known to work.**

## Appendix B · Regression baseline

| Scenario | Confidence | Plan |
|---|---|---|
| Payment, 49 cases | 0.974 → 0.974 | Accelerated, 3 agents |
| Order queue, weak history | 0.313 → 0.313 | Full, 5 agents |
| Payment, contradicted | 0.974 → 0.754 | Accelerated → Full |
| Payment, resolved | 0.974 → 0.854 | Accelerated |
| Cross-platform gateway | 0.765 → 0.865 | Full → Accelerated |
| Payment EU, by analogy | 0.872 → 0.872 | Full (transferred) |

## Appendix C · Running it

```
python rehearse.py                            # pre-demo gate, ~1 min, non-zero exit if not ready
python -m streamlit run eaios_story_app.py    # the demonstration
python demo_learning_loop.py                  # the learning arc in the console
powershell -File ./validate.ps1               # full suite
```

Full technical detail in `DESIGN.md`. Walkthrough script in `DEMO_SCRIPT.md`.
