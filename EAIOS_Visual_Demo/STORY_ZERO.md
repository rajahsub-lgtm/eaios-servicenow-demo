# Story 0 — Why this work

**An addition to the ServiceNow Storytelling Package**
The origin story that gives the other six their reason

---

## Why this story exists

The storytelling package establishes that you are a practitioner who
discovered an architecture. It is missing the answer to a question a good
panel always asks in some form:

> *"Why do you care about this?"*

Everyone in that room can build a reference architecture. Very few of them
have a reason to. This story is the reason, and it is the only one in the
portfolio nobody else can tell.

It also does analytical work, not just emotional work — which is what makes it
usable in a technical interview. The insight is structural:

> **A patient with a chronic condition across multiple specialists, insurers
> and years has the same problem as an application across multiple monitoring
> tools, teams and years. Nobody holds the whole picture over time.**

That is not a metaphor. It is the same architecture problem with a different
noun, and recognising it is what a systems architect is *for*.

---

## The rule for this story

**Say it once, precisely, then move to the consequence.**

The power is in the restraint. A panel that senses you are trading on personal
difficulty will discount everything after it; a panel that hears you state a
fact plainly and immediately draw an architectural conclusion from it will
remember you for a year.

You are not asking for sympathy. You are explaining why you noticed something
other people walked past.

---

## The 60-second version

> "My first project, twenty years ago, was electronic medical records — semantic
> ontology work, transcribing clinical records to build an expert system. We
> were trying to make a machine understand what a doctor had written.
>
> It mostly didn't work. Not because the idea was wrong. Because the muscle
> wasn't there. We could encode one hospital's ontology by hand. We could not
> connect the data.
>
> Some years later this stopped being academic for me. My wife and my child
> both have autoimmune conditions. Multiple specialists, over years — and the
> specialists change, the insurance changes, the records move. Every appointment
> starts by reconstructing the history. Nobody holds the whole picture over
> time.
>
> When I moved into application health I recognised the shape immediately. An
> application has the same problem: monitoring in one place, incidents in
> another, dependencies in a third, ownership somewhere else — and during a
> major incident, someone is reconstructing the history by hand while the
> business waits. Same problem. Different noun.
>
> So I built the enterprise capability for that: know what is healthy, know
> what it depends on, know what it means to the business, and heal it without
> waiting for someone to reassemble the context. About 80% fewer major
> incidents.
>
> What's changed since my EMR work is that the muscle now exists. Twenty years
> ago I was hand-building an expert system for one institution. Today the same
> reasoning can learn from outcomes across thousands of them. That is the
> difference between an expert system and collective intelligence — and it is
> why I think this is the most interesting moment of my career.
>
> It is also why I have spent it on governance. If we are going to connect
> that much health data — or financial data, or operational data — to find
> patterns nobody could see before, the governance question is not a
> compliance afterthought. It is the thing that decides whether it is allowed
> to happen at all. That is what EAIOS is for."

**Then stop.** Let them ask.

---

## The 25-second version

For when the room is moving fast, or you would rather keep the family detail
private:

> "My first project was electronic medical records — semantic ontology for an
> expert system, twenty years ago. It didn't really work; the muscle wasn't
> there. We could encode one hospital's knowledge by hand, we couldn't connect
> the data.
>
> Application health turned out to be the same problem with a different noun:
> the signals exist, nobody holds the whole picture over time, and somebody
> reconstructs it manually while the business waits.
>
> What's different now is that the muscle exists. An expert system becomes
> collective intelligence. That is why I've spent this stage of my career on
> making it governable — because at that scale, governance is what decides
> whether it is allowed to happen."

---

## Where it goes

### Option A — as the opening (recommended)

Put it in front of *"Tell me about yourself."* Twenty seconds of Story 0, then
straight into Application Health as the package already has it.

The two-minute opening currently begins:

> *"My career has focused on turning fragmented operational data into decisions
> and measurable business outcomes."*

That is a true sentence that could be said by two hundred people. Replace it
with:

> *"My first project was electronic medical records — semantic ontology for an
> expert system. Twenty years later I am still solving the same problem:
> fragmented data, no holistic picture, and someone reconstructing context by
> hand while it matters. That is what took me to application health, and what
> took me from there to governed AI."*

Then continue into Intel exactly as written. **Credibility → range → insight →
frontier** still holds; you have simply given it a starting point that is
yours.

### Option B — as the answer to "why this role"

The package's 30-second *"why ServiceNow"* is solid and generic. Story 0 makes
it specific: this is the platform where enterprise context, governance and
actual workflows of action already meet, which is the combination the problem
has always needed and never had.

### Option C — as the close

If the conversation has been technical throughout, this is the strongest
possible last ninety seconds. It reframes everything they have just heard as
purposeful rather than clever.

**Do not use it in all three places.** Once, deliberately.

---

## The arc it creates

| | Then | Now |
|---|---|---|
| **Knowledge** | Hand-encoded ontology, one institution | Learned from outcomes, across many |
| **Reasoning** | Rules an expert wrote down | Patterns recognised by presentation, weighted by what actually worked |
| **Limit** | The data could not be connected | It can |
| **Risk** | The system was wrong quietly and rarely | It can be wrong confidently and at scale |
| **Answer** | Better rules | **Governance** |

That last row is the whole argument for EAIOS, and Story 0 is what earns the
right to make it.

---

## The tie to what you built

This is not a rhetorical arc. It is the architecture of the demonstration, and
you can show it:

**The demo literally moves from expert system to collective intelligence.**

| Demo beat | The old world | The new world |
|---|---|---|
| Curated `known_errors` | The expert system. Someone wrote the pattern down | — |
| Reads the runbook (beat 5) | Still the expert system — a document an expert authored | — |
| Human validates, pattern minted (beat 6) | — | The transition. Knowledge the system arrived at, not knowledge it was given |
| Learns from outcome | — | Collective intelligence: what worked, what didn't, weighted by who established it |

> "The system starts where I started twenty years ago — with a written
> procedure an expert authored. Then a human validates a case, and it has a
> pattern nobody wrote down. That transition is the whole difference between
> the two eras, and it is beat six of the demo."

**The domain-independence is real, not aspirational.** The scenarios are data,
not code. The engine ignores the expected results in the scenario files and
derives its own. Change the entities from payment connectors to care pathways
and the reasoning does not change:

| Application health | Patient health | Financial health |
|---|---|---|
| Which systems are up | Which conditions are active | Which exposures are live |
| What depends on what | Comorbidity and interaction | Correlated risk |
| Recorded outcomes of remediations | Recorded outcomes of treatments | Recorded outcomes of interventions |
| Confidence from history, not assertion | Same | Same |
| A human approves the action | **Emphatically the same** | Same |

> "I built it for application health because that is where I could get the
> data and where nobody gets hurt if I am wrong. The reasoning is not specific
> to IT."

---

## Handling the frontier claim carefully

You want to say that AI may find answers to cancer or autoimmune disease. That
instinct is right and the claim needs shaping, because the guide's own warning
applies: **avoid overclaiming.** A prediction invites a sceptic; a stated
constraint invites agreement.

**Don't say:** *"AI is going to cure cancer."*

**Say:**

> "I don't know whether AI will find the answer to autoimmune disease. What I
> do know is why it couldn't before: nobody could connect the data. That
> constraint is gone. When the constraint on a problem changes, you should
> expect the problem to change — and that is worth being serious about."

That is unarguable, it is more interesting than the prediction, and it lands
the same emotional weight without exposing you.

**If asked directly whether you believe it:** *"I think it is now a question
about data governance and consent rather than a question about capability.
Which is exactly why I work on the governance."*

That answer turns the frontier question into a demonstration of your judgement
rather than your enthusiasm.

---

## Lesson lines

Add to the cheat sheet:

- **Story 0:** *Twenty years ago the idea was right and the muscle was missing. The muscle is here now — which makes governance the whole question.*
- **On domain transfer:** *Application health, patient health, financial health. Same architecture, different noun.*
- **On the era change:** *An expert system knows what someone wrote down. Collective intelligence knows what actually worked.*
- **On why governance:** *At this scale, being confidently wrong is the failure mode that matters.*

---

## A note on judgement

Only you can decide how much of the family detail to bring into a professional
room. Both versions above work — the 25-second one carries the whole
architectural argument without it.

What makes the longer version land, if you use it, is that you do not linger.
One sentence of fact, then straight to what you noticed as an architect. The
panel will understand exactly how much is behind it without you having to
spend any of it.

If someone responds personally, a simple *"thank you — it's why I care about
getting the governance right"* returns the conversation to your ground without
closing them off.

---

## The closing line

If you use Story 0 to end the conversation:

> "I started my career trying to get a machine to understand a doctor's notes,
> and it was too early. I have spent the twenty years since watching the
> constraint that stopped it disappear. What is left is whether we can do it
> safely enough to be allowed to — and that is the problem I want to work on,
> at the company best positioned to solve it."
