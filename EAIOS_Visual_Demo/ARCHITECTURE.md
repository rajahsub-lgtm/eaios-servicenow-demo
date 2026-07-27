# What was built

A working operational-reasoning system in which confidence is derived from
recorded outcomes, the investigation plan is a consequence of that confidence,
and no path reaches an action without a human.

The deck at `outputs/EAIOS_Architecture_and_Demo.pptx` walks through this for
an audience. This document is the reference behind it.

**Scale:** 30 entities, 46 governed relationships, 118 recorded outcomes, 20
knowledge documents, 9 scenarios, 468 tests.

---

## The claim

> Evidence changes confidence. Confidence changes the plan. The plan changes
> which agents run.

Everything below exists to make that true rather than asserted, and to make it
falsifiable in front of someone sceptical.

---

## Layers

Each answers one question and is not permitted to answer another's. Five
faults were found where two components derived the same judgement and reached
different answers, so the boundary is now enforced by tests rather than
convention.

| Layer | Module | Answers |
|---|---|---|
| Semantic graph | `graph_engine.py` | What exists, what it depends on, what a pattern is declared to cover |
| Experience ledger | `experience_ledger.py` | What has happened, and what each case is worth |
| Confidence engine | `operational_confidence_engine.py` | How alike is this case, how reliable is that pattern, what plan is warranted |
| Evidence fusion | `evidence_fusion_agent.py` | What to tell a human, and how to weigh sources against each other |

**The rule:** the confidence engine owns operational judgement; fusion owns
explanation and adjudication. A judgement made in the engine is *passed* to
fusion, never re-derived there. Both read experience through the ledger, so
neither can hold a different past.

---

## Concepts

### 1 · Operational confidence

Derived from `outcome_history.json` plus anything recorded at runtime, weighted
by three things applied once, in the ledger:

- **Recency** — half-life decay, so last month outweighs last year.
- **Provenance** — how the case was established. Human-verified 1.2, own
  outcome 1.0, peer agent 0.8. A rubber-stamped approval is *not* verification
  and is classed as a self-outcome; a human who amended or overruled engaged
  with the case and is.
- **Standing** — a peer agent's weight is bounded by its authority over the
  claim, not its general reliability. The telemetry agent is the more reliable
  of the two and counts for 0.08 against the vendor agent's 0.736 on a vendor
  advisory, because that claim is not its to make.

Two attenuation rules: **authority attenuates through delegation** and **trust
attenuates through transfer**. Neither ever amplifies.

Confidence is **asymmetric**: a contradiction costs up to 0.22 and applies in
full; recovery is capped at 0.10 per reassessment and can never exceed 0.95 at
runtime. Cycling evidence erodes confidence and cannot be used to manufacture
it.

*Policy:* `config/confidence_policy.json`, `config/experience_trust_policy.json`

### 2 · Dynamic planning

The plan is selected from confidence, drift, evidence coverage and hard flags —
not configured per scenario. It moves **during** execution in both directions:

- **Expansion** — contradictory knowledge widened a running plan from 3 agents
  to 6 while preserving completed work.
- **Contraction** — resolving evidence retired a hypothesis, narrowed the plan
  and cancelled work before it ran.

Plan *width* and agent *participation* are different measurements and are
always labelled separately, so a narrowing plan never looks like a
contradiction of the agents that informed it.

*Policy:* `config/orchestration_policies.json`

### 3 · Collective intelligence

Recall is by **presentation**, not by label. A case fingerprint describes
symptoms, structural position, impacted capabilities and blast radius; a
similarity score grades how alike two cases are.

This replaced boolean graph reachability, which answered *yes* for a familiar
component showing an unfamiliar symptom and *no* for an identical symptom on a
structural sibling — opposite failures, both wrong.

Recall is classified and discounted accordingly:

| Class | Meaning | Ceiling |
|---|---|---|
| `DIRECT` | Resolved here before | — |
| `TRANSFERRED` | Resolved on a sibling | 0.85 similarity, bars the narrow plan |
| `DOCUMENTED` | Only a written procedure | 0.45 confidence, bars the narrow plan |
| none | Nothing matches | governed non-diagnosis |

*Modules:* `case_fingerprint.py`, `case_similarity.py`, `documented_reasoning.py`

### 4 · Governance

Three tiers, every flag placed deliberately:

1. **Bars the narrow plan** — transferred experience, documentation-only,
   provisional pattern, previously ineffective remedy, recent high-risk change,
   vendor status unknown, previously rejected account.
2. **Suspends automation** — anything not backed by the system's own recorded
   outcomes. Readiness asks whether *this* system has earned the right to act
   unattended, and only its own history can answer.
3. **Informational** — reopened knowledge search, newer documentation
   available. These disclose and carry no plan effect.

Lower the HIGH confidence band from 0.85 to 0.30 and **nothing** gains a
shortcut. The flags are categorical, not advisory — that is the difference
between a threshold and a control, and the *Confidence controls* tab
demonstrates it live.

*Also:* a PDP/PEP policy layer governs agent-to-agent, tool and data access,
returning `ALLOW_WITH_OBLIGATIONS`, `ESCALATE` or `DENY`.

### 5 · Evidence fusion

Every source reaches a contribution ledger carrying its class, role,
reliability, contribution and the basis on which it was admitted.

Two retrieval paths read the same corpus and answer different questions:
lexical relevance to the graph neighbourhood, and whether a document is about
*this component and this symptom*. Neither is gated away. Material that cannot
support a cause is carried as context at reduced reliability contributing
nothing, with a rationale saying so — because it can still prompt a useful
human thought, and the point of a ledger is that a person sees everything
considered and what each thing was worth.

### 6 · Learning from outcome

The loop that turns a first encounter into a second:

1. **Never seen** — no pattern matches, so it reads the runbook. A cause is
   proposed with its source, owner and validation date named, and confidence
   capped below any level that could narrow a plan.
2. **Human validates** — confirmed, corrected or rejected. A correction is the
   most informative outcome and replaces the proposed cause.
3. **A pattern is minted** — written as an ordinary known error, marked
   provisional, so the next encounter recalls it through the normal path. A
   learned pattern needing a special lookup would not have been learned.
4. **Seen again** — 0.341 if the remedy worked, near zero if it did not. A
   failed remedy is carried forward as a *named fact*, not merely a lower
   average.

**Rejection is evidence, not a ban.** Support decays per rejection with a
floor, so a refuted account stays offerable when nothing better explains the
presentation — with the prior rejection and the name of who made it disclosed.
A human can reject wrongly, and a system that treats one rejection as final has
made that error unfalsifiable.

Promotion at 15 successful cases is evaluated from the record at read time, so
a falling success rate demotes without anything having to remember to.

*Modules:* `pattern_learning.py`, `outcome_feedback.py`

---

## The use case

A payment connector times out. Behind it: 30 entities, dependency and routing
relationships, recorded outcomes, known errors, changes, knowledge documents
and vendor advisories.

The graph illustration in the deck is the **cross-platform** case, which is the
clearest demonstration that relationships are traversed rather than declared:

```
GitHub Enterprise ──depends on──▶ Repo access ──routed through──┐
                                                                ├──▶ Secure web gateway ──depends on──▶ TLS policy
Microsoft Teams  ──depends on──▶ Signalling  ──routed through──┘                                          (changed 6h before)
```

Two unrelated-looking incidents converge on one component three hops away.
Nothing in either incident says they are related. Traversal is filtered to
authoritative relationships, so an inferred or low-confidence edge cannot
manufacture a connection.

---

## How it is held together

468 tests. The ones that matter architecturally:

| Suite | Defends |
|---|---|
| `test_story_shape.py` | Directions and orderings, not fixture values. A test pinning 0.974 breaks when data improves; these assert that a contradiction *lowers* confidence |
| `test_layer_agreement.py` | The two layers pick the same pattern, count the same cases, weight them the same way |
| `test_architecture_invariants.py` | No fact read by one layer only; no policy with an undeclared second interpreter; no judgement made twice |
| `test_demo_narrative.py` | The app cannot caption a scenario with a claim its own run contradicts |
| `test_app_integrity.py` | Static checks on the presentation layer, which no other test executes |

Each structural guard was verified by injecting the original fault and
confirming it fires. A guard nobody has seen fail is not known to work.

---

## Running it

```bash
python rehearse.py                              # pre-demo gate, ~1 min
python -m streamlit run eaios_story_app.py      # the demo
python demo_learning_loop.py                    # the learning arc in the console
python build_deck.py                            # rebuild the deck from current data
powershell -File ./validate.ps1                 # everything
```

See `DEMO_SCRIPT.md` for the six-beat walkthrough and the questions a panel
will ask.

---

## Boundaries

Synthetic data throughout. ServiceNow remains the system of record and the
approval control; this system proposes and never executes. Live PDI sync is
built but not wired into the demo path.
