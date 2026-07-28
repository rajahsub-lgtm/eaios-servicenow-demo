# The frame — for people who over-explain

**A one-page replacement for STAR**
Companion to the ServiceNow Storytelling Package

---

## The diagnosis

You do not have a story problem. You have an **ordering** problem and a
**stopping** problem.

STAR fails architects specifically. *Situation* and *Task* are two beats of
context before anything happens — and for someone who genuinely sees the whole
system, two beats of context expands to two minutes. By the time you reach
*Result*, the panel has stopped tracking and you have spent your credibility
on setup.

The Google XYZ formula — *"Accomplished X, as measured by Y, by doing Z"* — has
the right instinct and the wrong shape. Its insight is the **inversion**: lead
with the outcome so that context must earn its place instead of preceding it.
Its limitation is that it is a résumé bullet. It has no slot for the decision,
and the decision is what an architecture interview is actually buying.

---

## The frame: **Result · Tension · Decision · Stop**

Four beats. The fourth is silence.

| Beat | One sentence of… | Why it is here |
|---|---|---|
| **Result** | What changed, with a number | Buys attention. Everything after it is now justification, not preamble |
| **Tension** | What made it hard | Replaces Situation + Task. Not context — *conflict*. One sentence |
| **Decision** | What you chose, and what you chose against | The thing they are hiring. XYZ omits it; STAR buries it |
| **Stop** | *"I can go deeper on the mechanism if that's useful."* | A designed exit. This is the beat you are missing |

### Worked example — Application Health

> **Result.** "We took major incidents down about 80% and overall volume about
> 67%."
>
> **Tension.** "The tooling was already good. The problem was that during a
> major incident, someone was still reconstructing the application, its
> dependencies, its ownership and its business impact by hand — while the
> business waited."
>
> **Decision.** "So I treated it as a context problem rather than a monitoring
> problem. We didn't buy more observability; we connected what we already had
> into one health picture with ownership and business impact attached. The
> trade was that it needed cross-organisational agreement, which is slower
> than buying a tool and is why it lasted."
>
> **Stop.** "I can walk through how we handled the dependency data if that's
> useful."

Roughly forty seconds. It contains a number, a conflict, a judgement, a
trade-off, and an invitation. STAR would have taken two minutes and buried the
decision.

### Worked example — EAIOS

> **Result.** "I built a governed orchestration prototype where evidence
> changes confidence and confidence changes which agents run. It runs
> end-to-end with 468 tests behind it."
>
> **Tension.** "Most systems let the model assert its own confidence, and then
> the plan is fixed regardless. Both halves of that are wrong."
>
> **Decision.** "So confidence is derived from recorded outcomes, weighted by
> how each one was established — and governance sits inside the loop rather
> than at the exit. The consequence I had to accept is that the system is
> often *less* confident than a model would claim, and it refuses to
> accelerate more often than a demo would like."
>
> **Stop.** "I can show you the case where it declines to diagnose at all."

---

## Why "what you chose against" matters

A decision with no alternative is a description. The clause that makes you
sound like an architect rather than an implementer is almost always the second
half:

- *"We didn't buy more observability; we connected what we had."*
- *"Confidence is not the model's self-report."*
- *"It refuses to accelerate more often than a demo would like."*

Every one of those names a road not taken. That is what distinguishes
judgement from activity, and it costs you eight words.

---

## The stopping problem

The frame will not save you on its own. Over-explaining is not a structural
fault — it is a **permission** fault. You keep going because nothing has told
you it is safe to stop.

So build the exit into the sentence. Your review guide already has the phrase:

> *"I can unpack the runtime mechanism if useful."*

Use it as a full stop, not a filler. Say it, then **stop talking**. Silence
after an invitation is not awkward; it is the offer being considered. If you
fill it, you have withdrawn the offer and started a second answer.

**Three mechanical rules:**

1. **One number per story.** Not a dashboard. Two numbers halve the memory of
   both.
2. **One sentence per beat.** If a beat needs two, the second one is detail —
   it belongs after the invitation, if they take it.
3. **Never explain the connection to another story unless asked.** Your
   package is right: *a transition is one sentence, not a new presentation.*
   You see the system; let them discover it.

---

## When to use which frame

| Situation | Frame |
|---|---|
| "Tell me about a time…" | **Result · Tension · Decision · Stop** |
| "Tell me about yourself" | The two-minute arc in the package. Different job — that one is a map, not a story |
| "Tell me about something you built" | Result · Tension · Decision, then *offer the screen*: "I can run it" |
| A follow-up probe | Answer only the probe. One beat. Then stop |
| "Why do you care about this?" | Story 0 |

---

## The honest caveat

Frameworks are for rehearsal, not delivery. If you are consciously running
beats in the room you will sound like you are running beats. Practise until
the *ordering* is instinct — result first, conflict second, judgement third —
and then forget the labels.

The one thing worth keeping conscious is the fourth beat. **Stopping is the
skill.** Everything else is a habit you already have.

---

## The card

> **Result. Tension. Decision. Stop.**
> One number. One conflict. One choice — and what you chose against.
> Then the invitation, and silence.
