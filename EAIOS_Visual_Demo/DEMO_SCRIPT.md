# Demo script — six beats, ten minutes

Each beat raises the question the next one answers. That is what makes it an
argument rather than a feature tour, and it is why the order matters more than
the completeness.

**Before you start:** `python rehearse.py` — about a minute, and it prints
every number you are about to show. If it says NOT READY, do not open the app.

```
python rehearse.py
python -m streamlit run eaios_story_app.py
```

The app opens on beat 1. The sidebar selector is in narrative order.

---

## Beat 1 · It has seen this 49 times

**Screen:** Payment connector — stable evidence. `0.974 HIGH`, Accelerated
Validation, 3 agents.

**Say:** "A payment connector is timing out. The system has resolved this
pattern 49 times, and 48 of those worked. That recorded history is what
produces 0.974 — not a model's self-report, an outcome record. And because
confidence is high, it runs three agents instead of five. The plan is a
consequence of the evidence, not a setting."

**The number that matters:** 0.974, and the fact that it is *derived*. Point at
the three agents. Narrow plans are earned.

> **They will ask:** "Where does 0.974 come from?"
> Recorded outcomes weighted by recency and by how each case was established —
> the system's own execution, a human correction, or another agent's finding.
> They are not worth the same. Open **Evidence & trust** if they want the
> ledger.

---

## Beat 2 · Confidence can be lost mid-run

**Screen:** switch to *Payment connector — contradictory knowledge*.
`0.974 → 0.754`, Accelerated → Full Investigation, 3 → 6 agents.

**Say:** "Mid-run, a knowledge article surfaces that contradicts the leading
hypothesis. It is credible but not enterprise-approved. Notice what does *not*
happen: it is not promoted to truth and it does not replace the hypothesis. It
costs 0.22 of confidence, and the lower confidence requires more skills, and
more skills mean more agents. The plan widened because the evidence changed."

**Then switch to *contradiction resolved*:** `0.754 → 0.854`, back to
Accelerated.

**Say:** "Deeper evidence retires the alternative. The plan narrows again and
cancels work no longer justified. But look at the number — 0.854, not 0.974. A
contradiction costs up to 0.22 in full; recovery is capped at 0.10 per pass and
can never exceed 0.95 at runtime. Cycling erodes confidence. It cannot be used
to restore it."

**The number that matters:** 0.854 versus 0.974. The asymmetry is the
governance argument.

> **They will ask:** "Why not let it recover fully?"
> Because then an agent could manufacture confidence by cycling evidence.
> Penalties apply in full and immediately; credits are capped and withheld
> while any unresolved flag remains.

---

## Beat 3 · One cause, two platforms

**Screen:** *GitHub and Teams — shared gateway dependency*. `0.765 → 0.865`,
Full → Accelerated, 7 agents.

**Say:** "Two unrelated-looking failures: developers cannot reach GitHub,
meetings are dropping in Teams. Nothing in the scenario says they are related.
The system traverses the dependency graph and finds both route through the same
enterprise gateway, which had a TLS inspection policy change. One cause, two
platforms, discovered rather than declared."

**The number that matters:** the agent count going *up* while the plan narrows.
Plan width and participation are different measurements — that distinction is
on screen deliberately.

> **They will ask:** "Is the relationship hardcoded?"
> No — it is a graph traversal over authoritative relationships. Remove the
> edge and the discovery does not happen. `python demo_graph_reasoning.py`
> shows the traversal if they want it.

---

## Beat 4 · Never here, but fifty times next door

**Screen:** *Payment connector (EU) — experience by analogy*. `0.872 HIGH`, and
**still Full Investigation, 5 agents**.

**Say:** "This is a different component — the EU payment connector. Nothing has
ever been resolved on it. But the presentation matches a pattern resolved fifty
times on its sibling, so the system recognises it and confidence rises to
0.872. Now the important part: that is HIGH confidence, and it still runs the
full plan. The match is recorded as an analogy, and an analogy is not allowed
to buy the shortcut that firsthand experience earns."

**The number that matters:** HIGH confidence with the wide plan. This is where
most systems would cheat.

> **They will ask:** "How is similar defined?"
> By presentation, not by label: symptom overlap, structural position, declared
> applicability, blast radius. Weighted in policy, because how alike is alike
> enough is an operational judgement, not an engineering constant.

---

## Beat 5 · Never seen at all

**Screen:** *Search indexer — nothing comparable*. `0.450 LOW`, Full
Investigation, automation SUSPENDED.

**Say:** "Now something genuinely new. No pattern matches. The system does what
an experienced engineer does — it reads the runbook. It proposes a cause, names
the document it came from, its owner, and when it was last validated, and says
plainly that nothing comparable has been resolved here. Confidence is capped at
0.45, below the band that could ever narrow a plan. A written procedure is
evidence about what should work. It is not evidence that it works here."

**Then switch to *Licence reconciler — nothing written either*:** `0.000`.

**Say:** "And when there is no procedure either, it says so. No cause, no
borrowed remedy from an unrelated pattern, escalate for direction. Not knowing
is a finding, not a failure — and it is the answer that is hardest to get out
of a system that always wants to produce something."

**The number that matters:** 0.000 with a complete, useful output.

> **They will ask:** "Isn't that just giving up?"
> The output lists what evidence to gather and records the case so the
> resolution becomes experience. That is beat 6.

---

## Beat 6 · Seen once before, and it matters how that went

**Screen:** the **Learning loop** tab. This runs live — it is not a recording.

**Say:** "Same unseen incident. A human validates the proposed cause and
corrects it: the stalled merge was the symptom, not the cause. That correction
mints a pattern, marked provisional, one case, carrying which document it came
from and who confirmed it. Three weeks later the same presentation returns."

**Point at the two numbers side by side:**

**Say:** "If the remedy worked: 0.341, and it now recalls its own pattern
instead of the manual. If it did not: near zero, and the system carries a
specific fact — this was tried here and it did not help. Same pattern, same
presentation, different behaviour, because what happened last time is part of
what it knows. Both still run the full plan. One case is not experience."

**The number that matters:** the gap between the two branches.

> **They will ask:** "Why is 0.341 lower than the 0.45 it had from the manual?"
> Good question, and it is the honest answer: it has traded borrowed authority
> for its own evidence, and its own evidence is one case. Watch it climb —
> `python demo_learning_loop.py` shows the ladder to 15 cases, where the
> pattern promotes and stops being provisional.

---

## Optional · Confidence controls tab

Use this when someone challenges whether the plan really follows the evidence,
or asks what happens if you tune the thresholds. It re-runs every scenario
through the real orchestrator against whatever bands you set.

**Drag HIGH to 0.99.** The payment connector with 49 recorded outcomes loses
its shortcut and goes to the full plan. Say: "Confidence did not change — the
evidence is the same. What changed is how much confidence the shortcut costs."

**Now drag it down to 0.30.** Nothing gains a shortcut. Say: "Four of these
now clear the confidence band comfortably and every one still runs the full
investigation, because the flags against them are categorical. Confidence
decides how much investigation is proportionate. It does not decide whether
governance applies — and that is the difference between a threshold and a
control."

> **They will ask:** "So I could just turn governance off in config?"
> You can move what confidence buys. You cannot move what the flags forbid
> from here: transferred experience, documentation-only reasoning, a
> provisional pattern and a previously ineffective remedy each bar the
> accelerated plan and suspend automation regardless of any threshold.

---

## Closing

**Say:** "Five things, all governed. Confidence is derived from recorded
outcomes, not asserted. The plan follows the confidence. Experience transfers
by analogy and is discounted as one. Nothing unbacked by the system's own
outcomes can ever be automated. And every recommendation names its evidence and
requires a human. The interesting part is not that it gets the answer right —
it is that when it does not have an answer, it says so, and then learns."

---

## If you have three minutes, not ten

Beats 1, 2, and 5. Confidence is earned; contradiction costs it; and when it
knows nothing it says so. That is the whole argument, and beat 5 is the one
they will remember.

## Things to have ready

| Question | Where |
|---|---|
| Show me the evidence weighting | **Evidence & trust** tab, contribution ledger |
| Can it act on its own? | **Automation readiness** tab — every path is SUSPENDED or NOT_READY |
| How does it reach ServiceNow? | **ServiceNow control** tab, field mapping and approval boundary |
| Is any of this hardcoded to the scenario? | Scenario files carry no expected results; the engine ignores them |
| What happens with real data? | Synthetic throughout, and the boundary is in the ServiceNow tab |

## If something goes wrong

- **App will not start** → `pip install -r requirements.txt`. plotly has been
  missing before.
- **Numbers differ from this script** → the bundle is stale. Regenerate with
  `python demo_servicenow_storytelling.py`, then re-run `rehearse.py`.
- **A panel renders oddly** → switch scenario and come back; Streamlit caches
  aggressively. If it persists, fall back to `python rehearse.py`, which shows
  every number without the UI.
