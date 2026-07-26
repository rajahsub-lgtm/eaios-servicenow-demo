# Course correction plan

Agreed 2026-07-26. Findings are in `ARCHITECTURE_REVIEW.md`; this is what to
do about them. Baseline `203b67c`, 397 tests green.

## The problem in one sentence

Shared judgements have no single owner and nothing enforces agreement, so the
confidence engine and the evidence fusion agent keep independently deriving
the same thing and reaching different answers.

Four instances found. Fixing four bugs leaves the fifth free to appear, so the
sequence puts the invariant in place before the repairs.

## Governing rule to establish

> **The confidence engine owns operational judgement. Evidence fusion owns
> evidence explanation and adjudication between sources.**

A judgement made in the engine is passed to fusion, never re-derived there.
A source disagreement is not resolved by a gate upstream — it is carried into
fusion with its provenance and weighed there, which is what the contribution
ledger is for.

---

## Phase 0 · Lock the contract before fixing anything

**~1.5h · commit 1**

Write the agreement tests that should have caught all four faults. They will
fail on arrival, and that is the deliverable: the gaps become executable facts
with a target that later phases turn green.

- The two layers select the same pattern for every scenario.
- They count the same number of cases for the same pattern.
- They compute the same weighted success rate.
- They consider the same patterns admissible.
- Every fixture read by one layer is read by the other, or the asymmetry is
  declared with a reason.

Position is not negotiable. Repairing before the tests exist is how these
arrived.

## Phase 1 · One owner for history and admissibility

**~3h · commit 2 · fixes C1**

Extract a single component that owns both questions the layers currently
answer separately:

- **What history counts** — outcome rows for a pattern, including runtime
  feedback, with recency and provenance weighting applied *once*. Today the
  engine weights (0.47) and fusion counts raw (0.55) over the same 20 cases,
  so the number the human reads is not the number that chose the plan.
- **Which patterns are recallable** — the `Active`/`Provisional` and
  `Trusted`/`Provisional` admissibility filters, currently duplicated in both
  layers and already the source of one divergence.

Both layers read through it. Neither keeps a private copy of the rule.

Watch: fusion's hypothesis scores will move when its history becomes weighted.
Expect V1 numbers to shift and check each against the recorded table before
accepting it.

## Phase 2 · Let fusion adjudicate the knowledge sources

**~2h · commit 3 · fixes the two-path divergence**

Both paths stay. Neither is gated away upstream.

- `knowledge_retrieval_agent` keeps its lexical breadth — material a human
  might want to read is worth surfacing even when it cannot support a cause.
- `documented_reasoning` keeps its entity and symptom eligibility.
- Both emit into the evidence ledger **labelled with the path and the
  eligibility basis that admitted them**.
- Fusion weights accordingly: entity-matched and symptom-covered material may
  propose a cause; lexically-relevant-only material is carried as CONTEXT and
  cannot. The ledger states which, and why, for every item.

This is the existing mechanism doing its job rather than a new rule. Today
the ledger silently offers payment knowledge as context for a search-indexer
incident; afterwards it will still appear, marked as lexical-only and
contributing nothing to the hypothesis.

## Phase 3 · Close the remaining asymmetries

**~2h · commit 4**

- **Refutations attenuate learned patterns, not only documents.** The ledger
  has one reader today, so rejecting a cause lowers the document's support
  while a learned pattern built from that same cause is untouched.
- **Learned patterns enter the semantic graph.** `graph_engine.py` reads
  `known_errors.json` only, so a learned pattern participates in similarity
  and confidence but not traversal. Trace the consequences before changing —
  this is the least understood item on the list.
- **Reconcile promotion at 10 successful cases with
  `minimum_outcome_sample: 15`.** A pattern currently sheds its provisional
  penalty while still flagged as insufficiently evidenced. Two policies
  disagreeing about when experience is enough; pick one number and state why.

## Phase 4 · Prevent recurrence

**~1h · commit 5**

A structural test, in the spirit of `test_app_integrity.py` — static, no
runtime needed:

- Fails when a fixture is read by one layer and not the other.
- Fails when a policy file gains a second interpreter without declaration.
- Fails when a threshold constant appears in more than one module.

Also verify the outstanding candidate: `eaios_story_data.py` reads
`automation_readiness_policy.json` and `runtime_signal_policy.json` directly,
alongside the orchestrator. Two interpreters of one policy is the same shape;
confirm the UI cannot disagree with the run it displays.

---

## Must not be weakened

- Plan control belongs to operational confidence. The flags added last sprint
  (`WEAK_PATTERN_DOCUMENTATION_RECONSULTED`, `NEWER_DOCUMENTATION_AVAILABLE`)
  are informational and must not acquire plan effects.
- The three-tier flag taxonomy: blocks the narrow plan / suspends automation /
  informational. Every flag placed deliberately.
- Documentation is never experience: ceiling below MEDIUM, never narrows a
  plan, never displaces recalled experience as the lead.
- Rejection is evidence, not a ban.
- `test_story_shape.py` stays the frozen contract — directions and orderings,
  not values.

## Regression baseline

Any phase must reproduce these or explain the change:

| scenario | init → final | plan |
|---|---|---|
| SCN-PAY-001 | 0.974 → 0.974 | accelerated, 3 agents |
| SCN-QUEUE-001 | 0.313 → 0.313 | full, 5 agents |
| SCN-PAY-CONTRADICT-001 | 0.974 → 0.754 | accelerated → full |
| SCN-PAY-RESOLVED-001 | 0.974 → 0.854 | accelerated |
| SCN-CROSS-GATEWAY-001 | 0.765 → 0.865 | full → accelerated |
| SCN-PAY-EU-001 | 0.872 → 0.872 | full (transferred) |

```
python -m unittest discover -s . -p "test_*.py"
powershell -File ./validate.ps1
python demo_learning_loop.py
```

**Total ~9.5h, five commits.**
