# Phase 0 — containers · what was learned

**Status:** complete. Image builds, runs, serves the full demonstration.

---

## What was built

| File | Purpose |
|---|---|
| `Dockerfile` | The image definition, commented as a teaching artefact |
| `.dockerignore` | What never enters the build context |
| `requirements-runtime.txt` | Runtime dependencies, separated from development |

```
docker build -t eaios:0.1 .
docker run -d --name eaios -p 8600:8501 eaios:0.1
```

---

## Four things the container forced into the open

### 1 · Runtime dependencies are not development dependencies

`requirements.txt` declares six packages. The application imports three.
`pytest` runs tests, `python-pptx` builds the deck, `markdown` builds the
PDFs — none is reachable from `eaios_story_app.py`. Shipping them would
enlarge the image and widen what an attacker can execute inside it.

### 2 · Layer ordering is worth measuring, not assuming

Dependencies are copied and installed before the source. Measured on this
image:

| Build | Time |
|---|---|
| Cold — installs pandas, plotly, streamlit | **41 s** |
| After a source edit, dependencies unchanged | **4 s** |

Reverse those two `COPY` instructions and every code edit costs 41 seconds.

### 3 · The ignore file can break the app without failing the build

The first `.dockerignore` excluded `outputs/` wholesale. That directory holds
generated PDFs — and also `servicenow_story_bundle.json` and four CSVs, which
are the application's data.

The image would have built cleanly, started, and shown an empty repository.
Nothing warns you at build time that you excluded something the application
reads. Only the document types are excluded now.

### 4 · The entrypoint constrains what an override can mean

`ENTRYPOINT ["streamlit", "run"]` means every argument override must be a
streamlit argument. A different program cannot be run — deliberately, because
the image does one thing. Debugging needs an explicit override:

```
docker run -it --entrypoint /bin/bash eaios:0.1
```

---

## The architectural finding

**The reasoning is stateless. The experience is not.**

The learning loop writes three files into `json/` — `learned_patterns.json`,
`runtime_outcome_feedback.json`, `refutation_ledger.json`. Demonstrated
directly:

```
write learned_patterns.json inside the container   -> present
recycle the container                              -> file gone
```

A container filesystem does not survive the container. Cloud Run recreates
instances routinely, so a validated pattern learned at 10:00 is gone by 10:05,
and the demonstration would appear to work while silently losing everything it
learned. Worse, with more than one instance, two replicas would hold different
pasts — which is precisely the layer-divergence fault the architecture
correction exists to prevent, reappearing at the infrastructure layer.

**Consequence:** the experience ledger moves to Postgres in Phase 3. That
database was already needed for `pgvector`; it now has a second, independent
reason to exist — and shared state across replicas rather than per-container
state is the actual argument.

> "The reasoning layer is stateless and scales horizontally. The experience
> ledger is shared state and belongs in a database — the container made that
> decision for me rather than leaving it to be discovered in production."

---

## Image size — an honest observation

870 MB. Where it goes:

| Package | Size |
|---|---|
| pyarrow | 153 MB |
| pandas | 75 MB |
| plotly | 68 MB |
| numpy + numpy.libs | 70 MB |
| streamlit | 35 MB |
| pydeck | 23 MB |

`pyarrow` is the largest single item and arrives as a Streamlit dependency,
not a direct one. This matters for Cloud Run cold starts, where the image must
be pulled before the first request is served.

Not worth optimising yet — correctness first, and the numbers should be
measured on Cloud Run rather than guessed. Recorded here because "why is your
image 870 MB" is a fair question, and *"pyarrow, via Streamlit, and I would
measure cold-start impact before trading it away"* is a better answer than a
shrug.

---

## Checkpoint met

- [x] Image builds
- [x] Container serves the demonstration on a published port
- [x] Layer caching demonstrated by measurement
- [x] State loss demonstrated rather than assumed
- [x] The Phase 3 database now has two justifications

**Next:** Phase 1 — Artifact Registry and Cloud Run. Set budget alerts before
deploying anything.
