# Rev 1: saved RAG evidence review

Goal: extend the existing Evidence & trust tab with a readable payment RAG brief and its supplied evidence. Reuse the existing scenario selector, adaptive story, comparison, evidence fusion and governance panels.

## Scope
- One connected case: SCN-PAY-001.
- Load the existing local lab_evals/payment_rag_context.json and payment_rag_result_v1.json.
- Show brief, telemetry, accepted/conditional knowledge, structured records and generation metadata.
- Expose missing artifacts, malformed data, scenario mismatches and non-normal completion.
- Identify generated advice and legacy evidence linkage as unverified; do not invent evaluation scores.
- Preserve scenario plan, confidence, readiness and execution boundaries.

## Deferred
Live inference from Streamlit; vector/graph databases; new orchestration; automatic routing or remediation; source-link verification; saved reviewer approvals; additional evaluators; contradiction/shared-gateway AI briefs; recovery simulations. Existing stories remain available through their current dashboard views.

## Acceptance
1. Existing dashboard scenarios load.
2. Missing artifacts provide an informative empty state.
3. Payment artifacts appear only for the payment baseline.
4. Wrong-scenario, malformed or cutoff-mismatched artifacts are refused.
5. Conditional knowledge retains trust and limitation metadata.
6. Dashboard rendering invokes no Bedrock or MCP tools.
7. Existing story tests and focused panel tests pass.

## Use
Keep the two saved RAG JSON files in EAIOS_Visual_Demo/lab_evals. They were generated locally in the learning session and are not fabricated by this change.
Run `python -m streamlit run eaios_story_app.py`, select Payment connector — stable evidence, and open Evidence & trust.

The saved legacy result does not bind itself cryptographically to its input context. The panel deliberately displays an unverified-linkage notice. A later version can save context hashes with new generation results.
