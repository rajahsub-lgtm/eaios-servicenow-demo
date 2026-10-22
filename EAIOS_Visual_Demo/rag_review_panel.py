"""Read-only review of locally saved payment RAG artifacts; no cloud clients."""
import json
from pathlib import Path


class RagArtifactError(ValueError):
    pass


def load_payment_review(base: Path, scenario_id: str):
    if scenario_id != "SCN-PAY-001":
        return None
    folder = base / "lab_evals"
    paths = [folder / "payment_rag_context.json", folder / "payment_rag_result_v1.json"]
    if not all(p.exists() for p in paths):
        return None
    try:
        context, result = [json.loads(p.read_text(encoding="utf-8-sig")) for p in paths]
        if not isinstance(context, dict) or not isinstance(result, dict):
            raise ValueError("Artifacts must be JSON objects.")
        if context.get("scenario_id") != scenario_id:
            raise ValueError("Context belongs to a different scenario.")
        if not isinstance(result.get("brief"), str) or not result["brief"].strip():
            raise ValueError("Result has no investigation brief.")
        for key in ("telemetry", "accepted_knowledge", "conditional_knowledge", "structured_records"):
            if not isinstance(context.get(key), list) or not all(isinstance(x, dict) for x in context[key]):
                raise ValueError(f"Invalid context collection: {key}")
        for component in context["telemetry"]:
            if component.get("scenario_id") != scenario_id:
                raise ValueError("Telemetry belongs to a different scenario.")
            if component.get("as_of") != context.get("incident_time"):
                raise ValueError("Telemetry cutoff differs from the incident time.")
            if not isinstance(component.get("latest_readings"), list):
                raise ValueError("Invalid telemetry readings.")
        return context, result
    except (OSError, ValueError, TypeError) as exc:
        raise RagArtifactError(str(exc)) from exc


def render_rag_review(base: Path, scenario_id: str):
    import streamlit as st

    st.subheader("AI investigation brief · Rev 1")
    if scenario_id != "SCN-PAY-001":
        st.info("Rev 1 connects the saved payment RAG example only. This scenario has no connected AI brief.")
        return
    try:
        review = load_payment_review(base, scenario_id)
    except RagArtifactError as exc:
        st.error(f"Saved RAG artifacts could not be loaded: {exc}")
        return
    if review is None:
        st.info("Save payment_rag_context.json and payment_rag_result_v1.json in lab_evals to view the payment RAG example.")
        return
    context, result = review
    st.caption(f"Historical synthetic incident: {context.get('incident_time')} · Model: {result.get('model', 'Not recorded')} · Prompt: {result.get('prompt_version', 'Not recorded')}")
    st.warning("Generated advisory analysis. The legacy result has no context fingerprint: its link to the displayed evidence is unverified. It does not change the scenario plan, confidence, readiness or approval status.")
    if result.get("stop_reason") != "end_turn":
        st.warning("Generation did not report normal completion; the brief may be incomplete.")
    brief_tab, evidence_tab = st.tabs(["Generated brief", "Supplied evidence"])
    with brief_tab:
        st.markdown(result["brief"])
        st.caption("Quality evaluation: not recorded for this saved RAG result. Completion and citation checks alone would not establish completeness or justified remediation.")
        with st.expander("Recorded generation metadata"):
            st.json({k: v for k, v in result.items() if k != "brief"})
    with evidence_tab:
        st.markdown("**Telemetry and missing observations**")
        for component in context["telemetry"]:
            with st.expander(f"{component.get('component_id')} · {component.get('availability')}"):
                st.json(component)
        for key, title in [("accepted_knowledge", "Accepted knowledge"), ("conditional_knowledge", "Conditional knowledge")]:
            st.markdown(f"**{title}**")
            for item in context[key]:
                with st.expander(f"{item.get('chunk_id')} · {item.get('title')}"):
                    st.write(item.get("text", ""))
                    st.json({k: v for k, v in item.items() if k != "text"})
        with st.expander(f"Structured records ({len(context['structured_records'])})"):
            st.json(context["structured_records"])
        st.caption(context.get("retrieval_explanation", ""))
    st.info("Reviewer checks: consider database cause versus secondary effect; distinguish alert threshold from pool capacity; preserve conditional gateway evidence; verify remediation prerequisites. Record unresolved issues before any action.")
