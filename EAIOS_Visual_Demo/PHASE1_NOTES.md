# Phase 1 — Cloud Run · what was learned

**Status:** deployed and serving. Locked to authenticated access pending a
decision on §6.

```
Service   eaios-demo
Region    us-central1
URL       https://eaios-demo-536404360750.us-central1.run.app
Image     us-central1-docker.pkg.dev/enterprise-ai-operating-system/eaios/demo:0.1
```

---

## 1 · The guardrail went in first

No budget existed on the billing account. One now does — **$300 with alerts at
$51, $150 and $240**.

This is the only step that cannot sensibly be done later. Everything else in
this phase is reversible; a runaway bill is not, and the alert is what tells
you a mistake happened while it is still small.

## 2 · APIs are off by default

`run`, `artifactregistry` and `billingbudgets` all had to be enabled
explicitly. This confuses everyone once. It is a deliberate default: an
unenabled API cannot be called, cannot be billed, and cannot be attacked.

The budget API being disabled is a small trap — you cannot create the
guardrail until you enable the service that provides it.

## 3 · Registry, then push

```
gcloud artifacts repositories create eaios --repository-format=docker --location=us-central1
gcloud auth configure-docker us-central1-docker.pkg.dev
docker tag eaios:0.1 us-central1-docker.pkg.dev/PROJECT/eaios/demo:0.1
docker push us-central1-docker.pkg.dev/PROJECT/eaios/demo:0.1
```

`configure-docker` writes a credential helper into `~/.docker/config.json` so
`docker push` can authenticate as your gcloud identity. Without it the push
fails with a 401 that looks like a permissions problem and is actually a
missing helper.

## 4 · Four deployment settings that are decisions, not defaults

| Flag | Value | Why |
|---|---|---|
| `--memory=1Gi` | | The image carries pandas, pyarrow and numpy. 512Mi starts and then dies under load, which presents as random 503s |
| `--timeout=3600` | | Streamlit holds a long-lived websocket. The 300s default would sever a session mid-demonstration |
| `--session-affinity` | | See below — the important one |
| `--max-instances=3` | | A cost ceiling. Without it, a traffic spike or a loop can scale into real money |

`--min-instances=0` is the economic argument for Cloud Run: **idle costs
nothing.** The trade is cold starts.

## 5 · Session affinity — where Streamlit fights the platform

Cloud Run assumes stateless request handling and routes each request to any
instance. **Streamlit is not stateless.** It holds per-session server-side
state behind a websocket, so a user routed to a different instance mid-session
loses their context.

`--session-affinity` pins a client to an instance and papers over it.

The honest framing, and it is worth saying out loud:

> "Session affinity is a mitigation, not a fix. Streamlit is a stateful
> presentation layer, and I containerised it because it is the demonstration —
> not because it is the right shape for horizontal scale. The reasoning engine
> underneath it is stateless and would scale properly; if this were a product,
> the UI would be a thin client over an API rather than a server holding
> sessions."

That answer distinguishes someone who deployed a thing from someone who
understands what they deployed.

## 6 · Authenticated by default — a decision to make

Deployed with `--no-allow-unauthenticated`. Verified:

```
direct, unauthenticated  ->  HTTP 403
through the auth proxy   ->  HTTP 200
```

**Why locked:** `config/visual_demo.json` carries the PDI instance URL
(`dev392355.service-now.com`) and a record `sys_id`. Neither is a credential,
and a Cloud Run URL is effectively unguessable — but the repository was kept
private for exactly this reason, and making the same content public by a
different route without deciding to would be inconsistent.

**To make it public** once the decision is made:

```
gcloud run services add-iam-policy-binding eaios-demo \
  --region=us-central1 --member=allUsers --role=roles/run.invoker
```

**Recommended first:** replace the instance URL and `sys_id` in
`config/visual_demo.json` with placeholders. They are used only to render a
preview link in the ServiceNow tab. Roughly ten minutes, and then a public URL
carries nothing worth protecting.

## 7 · Measurements

| | |
|---|---|
| Warm response | **~0.30 s** |
| Image pushed | 870 MB, 3 layers |
| Cold start | not yet measured — needs ~15 min idle first |

Cold start is the number that matters for a demonstration, because the panel's
first click pays it. Worth measuring before the interview and, if it is bad,
`--min-instances=1` trades a few dollars a month for a warm instance. **Do not
set that yet** — measure first, then decide.

## 8 · Two things that wasted time

**`gcloud run services proxy` installs a component on first use.** The first
invocation appears to hang and then fails; the second works. Nothing says so.

**A blank Streamlit page with no console errors is a websocket problem, not a
rendering problem.** Confirmed here by testing the endpoints directly:

```
/_stcore/health   ->  200
/_stcore/stream   ->  101 Switching Protocols
```

Both healthy, so the app was fine and the browser pane was at fault. The
useful habit is to test the transport before debugging the application.

---

## Checkpoint met

- [x] Budget alerts live before any spend
- [x] Image in Artifact Registry
- [x] Service deployed, serving, scaling to zero
- [x] Access verified as locked
- [x] Streamlit's statefulness understood rather than worked around silently

## You can now say

> "Cloud Run because the workload is stateless, bursty and idle most of the
> time — scaling to zero is the whole economic argument. It stops being right
> when you need sidecars, per-pod scheduling or independently scaled
> components, which is exactly what the multi-agent topology needs, and that
> is why Phase 5 moves to GKE."

**Next:** Phase 2 — the synthetic data generator. Pure Python, no cloud, and
the long pole.
