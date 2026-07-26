# Architecture review — scope and findings

Opened 2026-07-25 at the end of the experience-transfer sprint, to be worked
through before further feature work. Branch `experience-transfer`, 397 tests
green at `a8f14e3`.

The trigger was a specific fault: the confidence engine and the evidence
fusion agent had each begun deciding, on their own scoring scales, whether a
recalled pattern was too thin to end the knowledge search. They reached
different answers about the same pattern. That was fixed by making it one
decision, owned by the confidence engine and passed to fusion — but the class
of fault is what matters, not the instance.

## The drift class

**Two layers deriving the same judgement independently.** Every occurrence so
far has produced a run where the plan was chosen on one premise and served by
a stage acting on another. It is not caught by unit tests, because each layer
is internally correct; it is only caught by asserting the layers agree.

Three instances were found and fixed during the sprint. All three predate it,
which is the reason for a full sweep rather than spot fixes.

| Found | Fault | Status |
|---|---|---|
| Reconsultation threshold | Both layers judged "thin recall" on different scales | Fixed — engine owns it, fusion is told |
| Runtime outcome feedback | Engine read `runtime_outcome_feedback.json`, fusion did not — the layers reasoned from different pasts | Fixed |
| Outcome lookup key | Fusion additionally required `scenario_pattern` to match; the engine matches on pattern identity alone. Redundant on shipped fixtures, silently wrong for anything recorded at runtime | Fixed |

## Confirmed gaps, not yet fixed

**1. Two knowledge paths over one corpus, with different rules.**
`knowledge_retrieval_agent.py` (lexical, tokens, trust gates) and
`documented_reasoning.py` (entity match, symptom coverage, trust, freshness)
both read `knowledge_documents.json` and disagree completely. For
`SCN-NOVEL-INDEX-001`:

```
retrieval agent        : KB-BUS-001, KB-PAY-001        <- payment docs, wrong component
documentation reasoner : RB-SEARCH-001, WIKI-SEARCH-014 <- correct
```

The retrieval agent's output is what fills the evidence ledger, so the ledger
currently shows payment knowledge as context for a search-indexer incident.
The documentation reasoner has an entity-match gate; the retrieval agent does
not. Decide whether retrieval should adopt the same eligibility rules, or
whether the two paths have genuinely different jobs — and if so, say so in
policy rather than leaving it implicit.

**2. Refutations attenuate documents but not learned patterns.**
`refutation_ledger.json` is read only by `documented_reasoning.py`. A human
rejecting a cause lowers the document's support, but a learned pattern built
from that same cause is unaffected. The asymmetry is unintended.

**3. Learned patterns are absent from the semantic graph.**
`graph_engine.py` reads `known_errors.json` but not `learned_patterns.json`,
so a learned pattern participates in similarity and confidence but not in
graph traversal. Consequences not yet traced — this is the least understood
of the three.

## Candidates to verify (unconfirmed)

- **Provenance weighting is applied in the confidence engine only.**
  `experience_trust_policy.json` has exactly one non-test reader. If fusion
  summarises outcome history unweighted while the engine weights by
  provenance and standing, the two layers again describe the same history
  differently. Needs a direct comparison before being called a defect.
- **`eaios_story_data.py` reads `automation_readiness_policy.json` and
  `runtime_signal_policy.json` directly**, alongside the orchestrator. Two
  interpreters of one policy is the same drift shape; check whether the UI
  can disagree with the run it is displaying.
- **`INSUFFICIENT_OUTCOME_HISTORY` still fires at 12 recorded cases** on the
  learned-pattern path. Either the threshold is wrong or the flag means
  something narrower than its name suggests.

## What to preserve

The review must not weaken these. They are the architecture, not decoration.

- Plan control belongs to operational confidence. Flags added this sprint are
  informational (`WEAK_PATTERN_DOCUMENTATION_RECONSULTED`,
  `NEWER_DOCUMENTATION_AVAILABLE`) and must not acquire plan effects by
  accident.
- The three-tier flag taxonomy: blocks the narrow plan / suspends automation /
  informational. Every new flag gets placed deliberately in one tier.
- Documentation is never experience. The ceiling sits below MEDIUM, a
  documented proposal cannot narrow a plan, and a documented score must never
  displace recalled experience as the lead on a numeric comparison.
- Rejection is evidence, not a ban.
- `test_story_shape.py` is the frozen contract. It asserts directions and
  orderings, not values, and it is what would catch plan-control drift.

## Verification to run first

```
python -m unittest discover -s . -p "test_*.py"
powershell -File ./validate.ps1
python demo_learning_loop.py
```

V1 planning as of `a8f14e3`, which any change must reproduce:

| scenario | init → final | plan |
|---|---|---|
| SCN-PAY-001 | 0.974 → 0.974 | accelerated, 3 agents |
| SCN-QUEUE-001 | 0.313 → 0.313 | full, 5 agents |
| SCN-PAY-CONTRADICT-001 | 0.974 → 0.754 | accelerated → full |
| SCN-PAY-RESOLVED-001 | 0.974 → 0.854 | accelerated |
| SCN-CROSS-GATEWAY-001 | 0.765 → 0.865 | full → accelerated |
| SCN-PAY-EU-001 | 0.872 → 0.872 | full (transferred) |
