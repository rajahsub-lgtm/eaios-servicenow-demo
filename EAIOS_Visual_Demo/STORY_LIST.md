# The story list — tomorrow

**Result · Tension · Decision · Stop**
One number. One conflict. One choice, and what you chose against. Then the
invitation, and silence.

---

## The order, and why

| # | Story | Establishes | Reach for it when |
|---|---|---|---|
| **0** | Why this work | Motive nobody else has | "Tell me about yourself" · "Why do you care" |
| **1** | Application Health | Production credibility at scale | The default opener. Everything rests on it |
| **2** | EAIOS + the demo | You built the thing the role is about | "Something you built" · anything on agents or governance |
| **3** | The buyer and the ZIP code | Governance with teeth | Human-in-the-loop · responsible AI · why governance |
| **4** | Knowledge-graph trust | Judgement, not just construction | Knowledge graphs · data quality · RDF/semantics |
| **5** | Formant | The pattern transfers, and you work with customers | Forward-deployed · multi-agent · outside IT |
| **6** | IMAP + Solution 360 | The substrate insight | AI inventory · discovery · Control Tower's *Discover* |
| **7** | Knowledge Intelligence | Grounding and retrieval trust | RAG · Now Assist · hallucination · knowledge ops |
| **8** | The lab report | The frontier, made concrete | The close, or "where is this going" |

**Bench** — do not volunteer, excellent if invited: the architecture
correction (§B1), Critical Action Review, Joint Intention Theory.

**Ordering logic:** 1 buys the right to be believed. 2 is the differentiator —
almost nobody in that chair has built and tested one. 3 makes governance
visceral in sixty seconds. 4 is the deepest thing you can say about data. 5–7
are range. 8 is the landing.

---

## 0 · Why this work

*Use once. Opening or close, never both.*

> **Result.** "My first project, twenty years ago, was electronic medical
> records — semantic ontology work, to build an expert system that could read
> a clinician's notes."
>
> **Tension.** "It mostly didn't work, and not because the idea was wrong. The
> muscle wasn't there. We could encode one hospital's ontology by hand; we
> could not connect the data. Years later it stopped being academic — my wife
> and my child both have autoimmune conditions, and across specialists and
> insurers and years, nobody holds the whole picture. Every appointment starts
> by reconstructing the history."
>
> **Decision.** "When I moved into application health I recognised the shape
> immediately. Same problem, different noun. So I spent a decade solving it
> for applications — and now the muscle exists, which turns an expert system
> into collective intelligence. That is why I have spent this stage of my
> career on governance rather than capability: at that scale, governance is
> what decides whether it is allowed to happen at all."
>
> **Stop.**

**Lesson line:** *Twenty years ago the idea was right and the muscle was
missing. The muscle is here — which makes governance the whole question.*

The 25-second version without the family detail is in `STORY_ZERO.md`. Decide
before you walk in, not in the room.

---

## 1 · Application Health

*The default opener. Your strongest verifiable outcome.*

> **Result.** "We took major incidents down about 80% and overall volume about
> 67%."
>
> **Tension.** "The tooling was already good — ServiceNow, BigPanda,
> Dynatrace, incident history, service dependencies. The problem was that
> during a major incident, someone was still reconstructing the application,
> its dependencies, its ownership and its business impact by hand, while the
> business waited."
>
> **Decision.** "So I treated it as a context problem rather than a monitoring
> problem. We didn't buy more observability; we connected what we already had
> into one health picture with ownership and business impact attached. The
> trade was that it needed cross-organisational agreement, which is far slower
> than buying a tool — and is why it outlasted me."
>
> **Stop.** "I can go into how we handled the dependency data, if that's
> useful."

**Lesson line:** *The signals existed. What was missing was the context, and
nobody owned assembling it.*

**Transition to 2:** *"That platform worked — and building it showed me the
next problem: we could not govern intelligent capabilities we had not
inventoried."*

---

## 2 · EAIOS + the demonstration

*The differentiator. You can put it on screen.*

> **Result.** "I built a governed orchestration system where evidence changes
> confidence and confidence changes which agents run. It runs end to end, with
> 468 tests behind it."
>
> **Tension.** "Most agent systems let the model assert its own confidence,
> then run a fixed plan regardless. Both halves are wrong. A model's
> self-report tells you how fluent the answer was, not whether the remedy has
> ever worked in that environment."
>
> **Decision.** "So confidence is derived from recorded outcomes — weighted by
> recency, by how each case was established, and by whether a human had to
> correct it. A pattern with 49 comparable outcomes starts on a narrow
> three-agent plan. Contradictory evidence mid-run drops confidence and
> expands to six while preserving completed work. Resolve the contradiction
> and it contracts again — but recovery is capped, because trust should be
> easier to lose than to regain. What I accepted in exchange is that it is
> often *less* confident than a model would claim, and refuses to accelerate
> more often than a demo would like."
>
> **Stop.** "I can show you the case where it declines to diagnose at all."

**Lesson line:** *Evidence changes confidence. Confidence changes the plan.
The plan changes which agents run.*

**The one line if you only get one:** *"Confidence determines depth, not
permission."* — and you can prove it in ten seconds by dropping the threshold
60% and showing that nothing accelerates.

---

## 3 · The buyer and the ZIP code

*Sixty seconds, and the most memorable thing you will say about governance.*

> **Result.** "I lived an AI governance failure as a customer, and it took a
> chargeback to correct it."
>
> **Tension.** "A package was marked delivered to the right ZIP code, and the
> automated dispute process treated that as proof it reached me. I appealed
> with evidence that it went to a different address in the same ZIP. The
> system reviewed the new evidence and made the same decision. Customer
> service could see it was wrong and had no authority to overturn it."
>
> **Decision.** "I stopped treating that as a model error, because it wasn't
> one — it was four failures. The design treated ZIP agreement as proof of
> address. The governance let a customer-adverse decision close without
> evidence proportional to the consequence. The appeal did not reduce
> confidence when contradictory evidence arrived. And the human could observe
> the error but not correct it. That fourth one is the one I built for."
>
> **Stop.**

**Lesson line:** *Giving AI the authority to deny a customer while denying
employees the authority to correct it is not human-in-the-loop. It is the
illusion of control.*

**Bridge to ServiceNow — say it, it is the strongest platform argument you
have:** *"ServiceNow can make human-in-the-loop real, because the evidence,
the decision record, the appeal path, the role-based authority and the audit
trail can live in one governed workflow. A human is not meaningfully in the
loop just because they can see the decision."*

---

## 4 · Knowledge-graph trust

*The deepest thing you can say about data. Judgement, not construction.*

> **Result.** "I had to answer a question I did not expect: how much should a
> system trust an edge that a human expert explicitly authored?"
>
> **Tension.** "I tried it both ways and both were wrong. Scoring purely on
> how the case presented discarded curated knowledge — a known error vanished
> from the very scenario it was written for. So I let the expert's declaration
> count directly, and got the opposite failure: the system matched a familiar
> component showing a completely unfamiliar symptom, because an expert had
> once declared the pattern applied there. Anchoring."
>
> **Decision.** "The mistake was reading the edge as a fact about a component
> when it was a claim about a *pattern* — and a pattern includes how it
> presents. So the declaration is admitted and then gated by the presentation:
> an expert saying 'this applies here' counts only to the extent the case
> actually looks like what was declared. In code it is one multiplication. In
> principle it is the difference between an edge as a fact and an edge as a
> conditional assertion."
>
> **Stop.** "I can show the case where it fires, if that's useful."

**Lesson line:** *An edge in a knowledge graph is not a fact. It is a claim,
by someone, at a time, about something — and the hard part is not storing it,
it is deciding how much to believe it today.*

**If probability comes up:** *"Confidence on an edge is not a calibrated
probability. It is an ordered trust score, and I do not claim it is Bayesian.
Calling it a probability when it has never been calibrated against outcomes
would be exactly the false precision the governance exists to prevent."*

---

## 5 · Formant

*Range: outside IT, customer-facing, and the multi-agent coordination point.*

> **Result.** "One system showed a 59.7% average reduction in time to
> resolution — about 581 hours over 540 days."
>
> **Tension.** "A manufacturing operations group had more alarms than
> technicians could investigate, and resolution depended on institutional
> knowledge held by a few experienced operators. I was not the domain expert.
> And the naïve architecture makes it worse: one root cause throws five
> alarms, so five agents confidently investigate the same problem in five
> different directions and return partial or contradictory findings."
>
> **Decision.** "So I owned the framing, integration and evaluation while the
> SME owned the process knowledge — and we built a coordinator that compares a
> new alarm against active investigations by structural and semantic
> similarity, then decides whether to share context, pause, or proceed
> independently. We also drew the line deliberately: about 66% of procedure
> steps were considered automatable, and the rest stayed with the human by
> design rather than by limitation."
>
> **Stop.** "Happy to go into how we evaluated it — it wasn't fluency."

**Lesson line:** *The hard problem in multi-agent systems is usually not
making one agent smarter. It is stopping agents from stepping on each other.*

**The image that does the work:** five agents, five alarms, one broken
component. Say it; people remember it.

---

## 6 · IMAP + Solution 360

*The substrate insight. Maps directly onto Control Tower's* Discover.

> **Result.** "The first serious pass found 108 agents operating inside Intel
> IT — 46 of them calling other agents, and 12 connected through MCP-style
> integrations."
>
> **Tension.** "It started because in a governance review someone asked how
> many AI agents we had. I didn't know. Nobody did. Teams were building faster
> than the enterprise could inventory what was being created."
>
> **Decision.** "So we captured ownership, capabilities, permissions,
> dependencies, data access, lifecycle and observability for each one. But an
> inventory on its own is only half — an agent also needs a reliable map of
> the enterprise, which is what Solution 360 gave us: services, applications,
> infrastructure, ownership, upstream and downstream dependencies. The
> inventory tells you who the actors are. The graph tells them what their
> actions could affect."
>
> **Stop.**

**Lesson line:** *You cannot govern what you have not inventoried — and you
cannot reason about consequence without a map.*

---

## 7 · Knowledge Intelligence

*Reach for it the moment RAG, Now Assist, grounding or hallucination comes up.*

> **Result.** "We improved knowledge quality by roughly 80% and contributed to
> about 45% call deflection."
>
> **Tension.** "We had a large amount of enterprise knowledge, and retrieval
> could find all of it with equal confidence — the useful, the stale, the
> duplicated, the incomplete, and the piece written for a different context.
> Retrieval can tell you what exists. It cannot tell you whether you should
> still trust it."
>
> **Decision.** "So we treated it as a lifecycle problem rather than a
> retrieval problem — automated analysis with Llama and ModernBERT plus human
> review, scoring relevance, duplication, freshness, lifecycle status and
> actionability, and then wiring those quality signals into self-service and
> operational outcomes. The consequence is that RAG stopped being an
> architecture and became an operating model with owners."
>
> **Stop.**

**Lesson line:** *RAG can retrieve what the enterprise has written. It cannot,
by itself, decide whether the enterprise should still trust it.*

---

## 8 · The lab report

*The frontier. Best as the close, or when asked where this is going.*

> **Result.** "I put my wife's lab report into an AI system and got a better
> account of it than we had received in the appointment — which numbers were
> moving, how her medication related to them, what was improving, what to
> consider tapering."
>
> **Tension.** "The tempting conclusion is that it beat the physician. It
> didn't. She has the accountability, the examination, the licence. What she
> didn't have was time to assemble four years of labs and a medication
> timeline before a fifteen-minute appointment. It didn't out-reason her. It
> out-*assembled* her — which is the same sentence I used about major
> incidents."
>
> **Decision.** "So the question I care about is the escalation. That was one
> lab result with none of her history. Give it her whole record, then every
> comparable patient on that medication, then the genetics and living
> conditions — and you have exactly the confidence model I built: her own
> history is direct experience, comparable patients are transferred
> experience, and the literature is documented-only, each weighted
> differently. What I will not claim is causation. Pattern-finding at that
> scale generates hypotheses; the confounders in observational health data are
> severe, and a system that blurs those two is dangerous."
>
> **Stop.**

**Lesson line:** *It didn't out-reason the doctor. It out-assembled her. Same
problem I spent a decade solving for applications — and the same reason it has
to be governed before it scales.*

---

## Bench stories

Do not volunteer. Strong if the conversation earns them.

### B1 · How I know the architecture holds

*The best answer to "how do you validate an architecture?"*

> **Result.** "I found five faults where two components independently derived
> the same judgement and reached different answers — and none of them was
> caught by a behavioural test."
>
> **Tension.** "The worst one: the explanation layer reported a 55% success
> rate on exactly the same twenty cases the planning layer had scored at 47%.
> Both were internally correct. So the number a human read was not the number
> that chose the plan, and nothing failed."
>
> **Decision.** "I stopped fixing the instances and fixed the class. One owner
> per judgement, then eleven tests asserting the two layers agree and eleven
> static guards that fail when a policy gains a second interpreter. And I
> verified each guard by re-injecting the original fault, because a guard
> nobody has seen fail is not known to work."
>
> **Stop.**

**Lesson line:** *Each layer was correct on its own. Correctness in isolation
is not the same as an architecture.*

### B2 · Critical Action Review — influence without authority

### B3 · Joint Intention Theory — shared goals, commitments, recovery

---

## Transitions — one sentence, never a new presentation

- **1 → 2** *"Building that showed me the next problem: we couldn't govern capabilities we hadn't inventoried."*
- **1 → 5** *"The obvious question was whether the pattern was specific to IT. Manufacturing let us test it."*
- **3 → 2** *"That made the requirement concrete: contradictory evidence must change the plan, and a human must have real authority."*
- **2 → 4** *"Building it forced a question I hadn't anticipated about how much to trust a curated edge."*
- **6 → 2** *"Knowing who the agents were solved half of it. They still needed to reason about consequence."*
- **anything → ServiceNow** *"The reasoning can be specialised. The record, the workflow, the approval and the outcome cannot."*

---

## The three rules

1. **One number per story.** Two halves the memory of both.
2. **One sentence per beat.** If it needs two, the second is detail — it goes after the invitation, if they take it.
3. **Lesson, then silence.** The invitation is a full stop. Filling the pause withdraws the offer and starts a second answer.

---

## The card

> **0** why · **1** app health · **2** EAIOS · **3** ZIP code · **4** graph trust
> **5** Formant · **6** inventory · **7** RAG · **8** lab report
>
> Result. Tension. Decision. Stop.
> *Confidence determines depth, not permission.*
