# EAIOS on GCP — a build-and-learn plan

**Two to three weeks · starting from zero on Docker and GCP · $300 trial credit**

---

## What "done" looks like

A live URL an Accenture panel can open, showing the governed reasoning system
you already have — now with real semantic retrieval, a language model doing
language work, running in containers, at a data scale that makes the knowledge
graph and RAG meaningful.

And, more importantly: **you can defend every component choice**, because you
made it rather than followed it.

### The claim you are building toward

> "I put a language model and a vector store into a governed system, and the
> governance did not change — because the model does language work and the
> ledger does judgement. That boundary is the product."

Accenture will be asked to build exactly this for clients. Most teams put the
model in the decision path. You will have a working demonstration of why that
is the wrong place, and what to do instead.

---

## The principle behind the order

**Fastest build order ≠ best learning order.** Take the learning order.

Each phase needs the concepts from the one before, so nothing is memorised
without a reason to remember it. Kubernetes comes *late* deliberately — people
who learn K8s before running a container in production end up with YAML they
cannot defend. By the time you reach it, Cloud Run will have taught you
stateless services, configuration, secrets, scaling and identity. Kubernetes
then becomes a familiar idea with more machinery, not a new world.

**Two tracks run in parallel.** The cloud track needs learning time. The data
generator (Phase 2) is pure Python on your laptop and is the long pole. Work
it in gaps.

---

## Phase 0 · Containers — day 1–2

*No cloud. No credits. Start here today.*

### Concepts

- **Image vs container.** An image is a filesystem snapshot plus metadata — a
  class. A container is a running instance of it. You build images; you run
  containers.
- **Layers and caching.** Each Dockerfile instruction creates a layer. Docker
  reuses unchanged layers, so instruction *order* decides rebuild speed. Copy
  `requirements.txt` and install *before* copying your source, or every code
  edit reinstalls every dependency.
- **Statelessness.** A container can be killed at any moment. Anything written
  inside it is gone. This is why `runtime_outcome_feedback.json` and
  `learned_patterns.json` become a real design question the moment you deploy
   — they are state, and they cannot live in the container.
- **ENTRYPOINT vs CMD.** Entrypoint is the executable; CMD is the default
  arguments. Getting this wrong is the most common reason a container exits
  immediately.
- **Multi-stage builds.** Build in a fat image, copy only artefacts into a
  slim one. Smaller images start faster and have less to attack.

### Build

A `Dockerfile` for the Streamlit app, a `.dockerignore`, and the app running
at `localhost:8501` **from inside a container**.

### Checkpoint

`docker run -p 8501:8501 eaios` serves the demo, and you can explain why the
image is the size it is.

### You can now say

> "The app is stateless by design. The learned patterns and outcome feedback
> are state, so on the cloud they move to Postgres — which is a design
> decision the container forced me to make explicit."

That last sentence is worth more than the Dockerfile.

---

## Phase 1 · Cloud Run — day 3–4

*First contact with GCP. This is where the credit starts.*

### Concepts

- **Projects and billing.** A project is the unit of isolation, quota and
  billing. Set a **budget alert at $50 and $150** before anything else.
- **APIs are off by default.** You enable each service explicitly. This will
  confuse you once, then never again.
- **Service accounts.** A non-human identity. Your Cloud Run service runs *as*
  one, and it should have only the roles it needs — this is the same
  least-privilege idea as your own agent registry with its `data_domains`.
- **Artifact Registry.** Where images live. Push from your laptop, pull from
  Cloud Run.
- **Cold starts and concurrency.** Cloud Run scales to zero, so the first
  request after idle pays start-up cost. Concurrency controls how many
  requests one instance handles — a real tuning decision, not a default.
- **Secret Manager.** Configuration that is not secret goes in environment
  variables; secrets go in Secret Manager and are mounted. Never in the image.

### Build

The container in Artifact Registry, deployed to Cloud Run, with a public URL.

### Checkpoint

You send someone a link and it works. Budget alerts are live.

### You can now say

> "Cloud Run because the workload is stateless, bursty, and idle most of the
> time — scaling to zero is the whole economic argument. It stops being right
> when you need sidecars, persistent local state, or fine-grained scheduling,
> which is the point where I'd move to GKE."

**Cost:** ~$0–3/month. Effectively free at demo traffic.

---

## Phase 2 · Synthetic data at scale — day 3–7, in parallel

*Pure Python. No cloud. The long pole, and the highest risk.*

### Why this is the risky part

Volume is easy. **Coherence is hard.** If incidents do not follow from
topology, and outcomes do not follow from incidents, the demo produces
nonsense that is visible to anyone paying attention — a confidence score
derived from history that contradicts the history shown beside it.

Your current 30 entities are hand-crafted and coherent. Scaling to thousands
means the *generator* must enforce what you previously enforced by hand.

### Concepts

- **Referential integrity.** Every `entity_id` referenced must exist. Every
  outcome must point at a real pattern. Generate in dependency order.
- **Realistic distributions.** Incidents are not uniform. A few components
  cause most incidents; most components cause none. Use a power-law-ish
  distribution or the data will feel synthetic even when it is consistent.
- **Causal chains.** A change on a component should raise the probability of
  an incident on it and its dependents within a window. That is what makes the
  change-correlation reasoning meaningful rather than decorative.
- **Outcome plausibility.** Success rates should vary by pattern in a way that
  makes some patterns trustworthy and others not — otherwise every confidence
  score lands in the same band and the demo has nothing to show.

### Build

A generator producing roughly:

| Fixture | Target | Why that size |
|---|---|---|
| Entities | ~2,000 | Enough that traversal is non-trivial |
| Relationships | ~15,000 | Multi-hop paths with real branching |
| Known errors | ~300 | Enough for similarity to have to discriminate |
| Outcome history | ~50,000 | Confidence bands genuinely separate |
| Knowledge documents | ~3,000 | ~20k chunks after chunking — real RAG scale |
| Incidents / changes | ~10,000 / ~2,000 | Correlation has something to find |

**Use Gemini to write the prose** — KB article bodies, incident descriptions,
symptom text. A few dollars of Flash tokens beats hand-writing three thousand
articles, and it makes the corpus linguistically varied, which is exactly what
semantic retrieval needs to prove itself against lexical.

### Checkpoint

The generated data loads and your **existing 468 tests still pass** against
it. That is the acceptance criterion — you already own a validation suite, so
use it.

### You can now say

> "The hard part of synthetic data is not volume, it is coherence. I generate
> in dependency order and validate with the same suite that guards the real
> fixtures, because incoherent demo data fails in ways an audience can see."

---

## Phase 3 · Real RAG — day 8–10

*The first genuinely new capability.*

### Concepts

- **What an embedding is.** A model maps text to a vector such that similar
  meanings land near each other. "Connection pool exhaustion" and "thread
  starvation" end up close; lexical search finds neither from the other.
- **Chunking.** You embed chunks, not documents. Size and overlap are real
  decisions: too small loses context, too large dilutes the signal. Chunk on
  semantic boundaries — sections, not character counts — where you can.
- **Cosine similarity.** Compares direction, not magnitude. It is the default
  for text embeddings and you should know why: magnitude carries length, not
  meaning.
- **Indexes.** Exact search is fine at 20k chunks. HNSW and IVFFlat are
  approximate indexes that trade a little recall for a lot of speed — worth
  understanding even if you do not need one yet.
- **Retrieval evaluation.** This is what separates people who have *used* RAG
  from people who have *shipped* it. Build a small labelled set — "for this
  query, these chunks are relevant" — and measure recall@k. Without it you are
  guessing.

### Build

Cloud SQL Postgres with the `pgvector` extension, Vertex AI embeddings, and
your retrieval agent switched from lexical to semantic — **with the eligibility
gating kept in place.**

### The thing that makes it *yours*

Plain RAG returns whatever is nearest. Your system already labels each
retrieved item with the basis on which it was admitted, and refuses to let
lexically-relevant-but-off-target material support a cause. **Semantic
retrieval plus governed eligibility is the demo.** Everyone has the first
half.

### Checkpoint

The search-indexer case that currently returns payment documents returns
search documents — and you can show recall@k before and after.

### You can now say

> "Retrieval quality is a data problem before it is a model problem. Better
> embeddings will not fix bad chunking, and neither fixes the absence of an
> eligibility rule about what a document is allowed to support."

**Cost:** Cloud SQL ~$10–15/month — **stop the instance between sessions** and
it is ~$1. Embeddings ~$1 one-time.

---

## Phase 4 · Gemini in three lanes — day 11–12

*Where the architecture argument lives.*

### Concepts

- **System instruction vs user content.** Role and constraints go in the
  system instruction; the case goes in the content. Mixing them makes
  behaviour unpredictable.
- **Structured output.** For extraction, demand JSON against a schema. Free
  prose that you then parse is a bug waiting to happen.
- **Temperature.** Zero for extraction. Extraction is not a creative task and
  variability there is pure downside.
- **Failure modes.** It will hallucinate an entity that does not exist, refuse
  occasionally, and be slower and more variable than your Python. Every one of
  those needs a defined behaviour — which is a governance question, and you
  already have the vocabulary for it.
- **Token accounting.** Know your cost per assessment. Accenture will ask.

### The three lanes — and the boundary

| Lane | The model does | The ledger still does |
|---|---|---|
| **Extract** | Free-text alert → entity, symptom, severity | Resolve to canonical entity; reject unknown ones |
| **Retrieve** | Embeddings for semantic similarity | Eligibility, weight, admission basis |
| **Narrate** | Turn the evidence ledger into prose | Produce every number the prose quotes |

**The model never computes a number that appears in the output.** It narrates
numbers the ledger produced. That is testable, and you should write the test —
it is the strongest possible evidence for the claim.

### Checkpoint

A free-text alert — *"payments are timing out for EU customers since about
2pm"* — flows through extraction into a full governed assessment with a
narrated explanation, and the narration's figures match the ledger's exactly.

### You can now say

> "The model reads and writes. It does not decide. I can show you the test
> that fails if a number in the explanation was not produced by the evidence
> ledger."

**Cost:** ~$10–20 total across development and demos on Flash.

---

## Phase 5 · Kubernetes — day 13–14

*Now it will mean something.*

### Concepts

- **Desired state reconciliation.** This is the whole idea. You declare what
  should be true; a controller works continuously to make reality match. Every
  other concept is a consequence.
- **Pod, Deployment, Service.** A pod is one or more co-located containers.
  A Deployment manages replicas of a pod and handles rollout. A Service gives
  them a stable address.
- **ConfigMap and Secret.** The same separation Cloud Run taught you, with
  explicit objects.
- **HPA.** Horizontal Pod Autoscaler — scale on CPU, memory, or a custom
  metric. Queue depth is the interesting one for agent workloads.
- **Autopilot vs Standard.** Autopilot manages nodes for you and bills per pod
  request. Standard gives you node control and more ways to be wrong.

### Build

The same image on GKE Autopilot. A Deployment, a Service, an HPA. Then — the
part that makes it an *architecture* story — **the agents as separately scaled
services**, because they have genuinely different resource profiles.

### Checkpoint

`kubectl scale`, watch it reconcile. Then delete the cluster.

### You can now say

> "Cloud Run and GKE are the same ideas with different amounts of control.
> I moved to GKE for the multi-agent topology — the telemetry agent and the
> retrieval agent have different resource profiles and different scaling
> triggers, and Cloud Run gives you one dial for the whole service."

**Cost:** ~$3–5/day. **Create it, demo it, delete it.** A forgotten Autopilot
cluster is the single fastest way to burn the credit.

---

## Phase 6 · Graph at scale — day 15

### Concepts

- **Property graph vs RDF.** Neo4j is a property graph: nodes and edges carry
  key–value properties. RDF is triples with formal semantics. Your EAIOS 3
  deck talks RDF/OWL; Neo4j is the pragmatic engineering choice and knowing
  the difference is the answer to a likely question.
- **Cypher.** Pattern-matching syntax. Your cross-platform traversal is about
  four lines.
- **When a graph database earns its place.** Not at 46 edges. At 15,000, with
  variable-depth traversal and path queries, it does.

### Build

Neo4j in a container, your topology loaded, the shared-gateway traversal as a
Cypher query.

### You can now say

> "At 46 relationships a graph database is overhead. At 15,000 with
> variable-depth path queries it is the right tool — and that threshold is the
> useful answer, not 'graphs are better.'"

**Cost:** near zero in a container.

---

## Phase 7 · Observability and unit economics — buffer days

- Structured logging with the correlation ID you already carry
- Cloud Trace across the assessment pipeline
- **Cost per assessment**: embeddings + LLM tokens + compute

> "About X cents per assessment, and here is the breakdown."

Very few candidates can say that. Accenture prices delivery — it lands.

---

## Budget guardrails

| Control | Effect |
|---|---|
| Budget alerts at $50 / $150 on day one | The one thing that prevents a bad surprise |
| **Never use Vertex AI Vector Search** | Deployed index endpoints bill per hour regardless of traffic — $300+/month. It would consume the entire credit while you sleep. pgvector is the right answer at this scale |
| **Never use Spanner Graph** | ~$70–90/month standing for a demo graph. Neo4j in a container instead |
| Stop Cloud SQL between sessions | ~$15/month → ~$1/month |
| Delete GKE after each session | ~$100/month → ~$4/day |
| Gemini Flash, never Pro | Order of magnitude cheaper, entirely adequate here |

**Expected total: $80–120.** You have room to make mistakes.

**Watch the expiry, not the balance.** Trial credits typically expire ~90 days
after activation regardless of how much is left.

---

## If the timeline compresses

Degrade in this order — each still leaves a coherent demo:

1. Drop **Phase 6** (Neo4j). Keep the in-memory graph; explain the threshold.
2. Drop **Phase 5** (GKE). Cloud Run plus manifests you can walk through.
3. Reduce **Phase 2** scale. 500 entities and 10k outcomes still demonstrates
   everything; only the "at scale" claim softens.

**Never drop Phases 3 and 4.** Semantic retrieval and the LLM boundary are the
whole reason for the exercise.

---

## What to do first

**Today, before any cloud account:** write the Dockerfile and get the app
running in a container locally. It costs nothing, it is the foundation of
every later phase, and it will immediately raise the state question that
shapes the whole design.

**Then** set the budget alerts, before deploying anything.
