# EAIOS 3 — story points for tomorrow

Extracted from the External Architecture Review deck, filtered to what is
*sayable* and, where possible, *showable*.

---

## The four lines to have in your mouth

These are the strongest sentences in the deck. Each is short, memorable, and
survives being repeated back to you.

> **"Confidence determines depth, not permission."**

The best line in the deck and the one your demo proves live. Drop the
confidence band from 0.85 to 0.30 and nothing accelerates. Use it whenever the
conversation touches autonomy.

> **"Authority attenuates through delegation. Outcomes improve belief, not
> authority."**

The safety property of the learning loop. A system that learns and can thereby
widen its own permissions is the failure mode everyone is quietly afraid of.
Yours cannot: validated outcomes move confidence and never touch scope.

> **"Semantic richness stays off the hot path."**

OWL and SHACL at design-time and ingestion; compiled deterministic controls at
runtime. This is the answer that separates people who have read about
knowledge graphs from people who have had to run one.

> **"No audit, fail closed."**

High-impact activity without correlation, evidence and policy references does
not proceed. One clause, and it tells them how you think about risk.

---

## The knowledge-graph trust story

**This is the one you asked about, and it is the strongest story in the deck —
because you did not just design it, you hit the problem and had to solve it.**

### Why it lands

Most people talk about knowledge graphs as though edges are facts. They are
not. **An edge is an assertion** — made by someone, at some time, with some
authority, and it may since have become wrong. Your graph already treats them
that way: every relationship carries `relationship_authority`,
`confidence`, `provenance`, `source_system`, `valid_from` and `valid_to`.

```
42 AUTHORITATIVE · 2 OBSERVED · 2 INFERRED     confidence 0.78 – 1.00
```

Traversal is filtered to authoritative edges, so an inferred or low-confidence
relationship cannot manufacture a connection.

But that is the easy half, and it is where most graph work stops.

### The hard half — told as Result · Tension · Decision · Stop

> **Result.** "I had to solve a problem I did not expect: how much should the
> system trust an edge that a human expert explicitly authored?"
>
> **Tension.** "I tried it both ways and both were wrong. When I scored
> similarity purely on how the case presented, curated knowledge got
> discarded — a known error vanished from the very scenario it was written
> for, because the presentation was slightly unusual. So I let the expert's
> declaration count directly. Then the opposite failure appeared: the system
> matched a familiar component showing a completely unfamiliar symptom, purely
> because an expert had once declared the pattern applied there. Anchoring.
> The expert edge was being read as a fact about the component, when it was
> really a claim about a *pattern*."
>
> **Decision.** "So the declaration is admitted and then gated by the
> presentation. An expert saying 'this pattern applies here' is strong
> evidence — but a pattern includes how it presents, so the declaration only
> counts to the extent the case actually looks like what was declared. In
> code it is one multiplication. Conceptually it is the difference between
> treating an edge as a fact and treating it as a conditional assertion."
>
> **Stop.** "I can show you the case where it fires, if that's useful."

### The lesson line

> **"An edge in a knowledge graph is not a fact. It is a claim, by someone,
> at a time, about something — and the hard part is not storing it, it's
> deciding how much to believe it today."**

### Why this is better than a governance-framework answer

Anyone can say "we track provenance and confidence on edges." Very few can
describe a case where **the expert was right and trusting them was still
wrong**. That is a real finding, and it demonstrates you have operated a graph
rather than diagrammed one.

It also answers the review guide's own framing perfectly:

> *"Solution 360 showed what was connected. The next maturity level is proving
> why we believe the connection, how current it is, who asserted it and
> whether outcomes continue to validate it."*

**You now have the fourth clause implemented.** Outcomes validate the
assertion: a human rejecting an account attenuates it — decays its support with
a floor, so it stays offerable when nothing better explains the case, with the
rejection and the rejector disclosed. Rejection is evidence, not a ban,
because a human can reject wrongly and a system that treats one rejection as
final has made that error unfalsifiable.

---

## The probability point, said carefully

If the conversation goes toward probabilistic graphs, this is the position:

> "I do not run probabilistic inference over the graph at runtime, and I would
> be cautious of anyone who says they do at enterprise latency. What I do is
> narrower and more useful: every assertion carries a confidence and an
> authority, retrieval is filtered by them, and the *reasoning* over the
> retrieved evidence is where uncertainty is combined — with the weights in
> policy rather than in code, because how much a stale edge should count is an
> operational judgement, not an engineering constant."

**And the honest limit, offered before it is asked:**

> "Confidence on an edge is not a calibrated probability. It is an ordered
> trust score, and I do not claim it is Bayesian. Calling it a probability
> when it has never been calibrated against outcomes would be exactly the kind
> of false precision the governance is supposed to prevent."

That last paragraph will land harder than any claim you could make. It is the
sentence of someone who knows the difference between a number and a
probability.

---

## Three more points worth having ready

### 1 · The action taxonomy

Slide 8 is a strong artifact — six action classes, each with a governance
posture, from read-only through to irreversible/regulated. **Reference it
rather than reciting it.**

> "I classify actions rather than treating them as one thing. Read-only is a
> fast path with authorisation and audit. Deterministic self-healing —
> restart, clear cache, scale — can be pre-approved when it is bounded,
> reversible and monitored. A material business write like a refund or a claim
> denial needs evidence sufficiency, human approval and an appeal path. And
> money movement or clinical action is blocked outright when a
> non-compensatory harm boundary is crossed."

**The clinical example is worth saying** given your story. It shows the
taxonomy is not IT-shaped.

### 2 · Storm mode and graceful degradation

Slide 10, and almost nobody at interview has thought about it:

> "The part people forget is what the system does when it is overwhelmed.
> Storm mode caps retrieval, model and tool budgets and degrades to
> monitor-or-advisory. A source outage falls back to last-known-good context
> with a freshness penalty rather than pretending the data is current. And
> human review saturation is a real failure mode — if every recommendation
> needs approval and the queue is four hundred deep, you have not built
> governance, you have built a bottleneck. So the queues are capacity-aware
> with sampling and stop conditions."

That last sentence is excellent. **Human review that does not scale is not
governance** — it is the appearance of governance, and it is a strong,
slightly contrarian point.

### 3 · Two-speed memory

> "Remember patterns, not every detail. Compact fingerprints decide whether
> deeper retrieval is justified; the raw record stays source-owned and gets
> pulled only when the pattern says it is worth it."

**And you can show pattern memory running** — it is the case fingerprint, and
it is what makes the second encounter behave differently from the first.

---

## What to avoid from this deck

| Risk | Why | Instead |
|---|---|---|
| **RLOO** | Collides with REINFORCE Leave-One-Out and invites a correction | **Operational Outcome Calibration** |
| Reciting the nine design principles | It becomes a document reading | Use two, land them, stop |
| Reciting the seven layers | Same | Name four and offer the rest |
| "Signed attenuated delegation" as though built | It is designed; `policy_layer.py` has no tokens, ceilings or expiry | "PDP/PEP is built. Signed attenuation is designed — I can walk the token structure" |
| OWL/SHACL as though built | Not implemented | "Design-time layer. In the demo the compiled artefacts exist as policy files; the layer that would generate them does not" |

---

## The single highest-value thing in this deck

**"Confidence determines depth, not permission."**

It is the thesis of your architecture, it is the thing your demo proves in ten
seconds with a slider, and it is the exact distinction most agentic systems get
wrong. If tomorrow gives you one sentence, that is the one — and you can put
evidence behind it immediately.

Everything else in the deck is support.
