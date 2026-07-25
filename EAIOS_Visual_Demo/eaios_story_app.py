from __future__ import annotations

from pathlib import Path
from typing import Any
import html

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from eaios_story_data import StoryDataError, StoryRepository, format_identifier


BASE_DIR = Path(__file__).resolve().parent

st.set_page_config(
    page_title="EAIOS Adaptive Operations",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def load_repository() -> StoryRepository:
    return StoryRepository.load(BASE_DIR)


def inject_css() -> None:
    st.markdown(
        """
        <style>
          .block-container {padding-top: 1.7rem; padding-bottom: 3rem; max-width: 1540px;}
          [data-testid="stSidebar"] {border-right: 1px solid rgba(128,128,128,.25);}
          .eaios-hero {
            border: 1px solid rgba(128,128,128,.28);
            border-radius: 18px;
            padding: 1.25rem 1.4rem;
            margin-bottom: 1rem;
            background: linear-gradient(135deg, rgba(84,96,255,.10), rgba(0,180,170,.07));
          }
          .eaios-eyebrow {font-size: .77rem; letter-spacing: .12em; text-transform: uppercase; opacity: .72;}
          .eaios-title {font-size: 2rem; font-weight: 750; line-height: 1.18; margin: .2rem 0 .35rem;}
          .eaios-subtitle {font-size: 1rem; opacity: .78; max-width: 1120px;}
          .eaios-callout {
            border-left: 5px solid currentColor;
            border-radius: 10px;
            padding: .8rem 1rem;
            margin: .5rem 0 1rem;
            background: rgba(128,128,128,.08);
          }
          .eaios-section-label {font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; opacity: .68;}
          .eaios-plan {
            border: 1px solid rgba(128,128,128,.28);
            border-radius: 14px;
            padding: 1rem 1.1rem;
            min-height: 160px;
            background: rgba(128,128,128,.045);
          }
          .eaios-plan-title {font-weight: 700; font-size: 1.05rem; margin-bottom: .6rem;}
          .eaios-arrow {font-size: 2rem; text-align: center; padding-top: 2.7rem; opacity: .7;}
          .skill-chip {
            display: inline-block;
            margin: .16rem .15rem .16rem 0;
            padding: .25rem .52rem;
            border-radius: 999px;
            border: 1px solid rgba(128,128,128,.3);
            font-size: .78rem;
            background: rgba(128,128,128,.08);
          }
          .skill-chip.added {font-weight: 650;}
          .skill-chip.cancelled {text-decoration: line-through; opacity: .55;}
          .eaios-conflict {
            border: 1px solid rgba(128,128,128,.28);
            border-radius: 14px;
            padding: 1rem;
            margin-bottom: .8rem;
            background: rgba(128,128,128,.05);
          }
          .eaios-kv {display:grid;grid-template-columns:175px 1fr;gap:.35rem .8rem;font-size:.92rem;}
          .eaios-kv div:nth-child(odd) {opacity:.7;}
          .eaios-footer {margin-top:2rem;opacity:.62;font-size:.82rem;text-align:center;}
          div[data-testid="stMetric"] {
            border: 1px solid rgba(128,128,128,.25);
            border-radius: 14px;
            padding: .65rem .8rem;
            background: rgba(128,128,128,.035);
          }
          div[data-testid="stMetric"] label {font-size:.8rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def safe_text(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def metric_row(assessment: dict[str, Any], preview: dict[str, Any]) -> None:
    conceptual = preview.get("conceptual_values", {})
    initial_score = float(assessment["initial_confidence_score"])
    final_score = float(assessment["final_confidence_score"])
    confidence_delta = final_score - initial_score
    initial_agents = int(assessment["initial_agent_count"])
    final_agents = int(assessment["final_agent_count"])

    cols = st.columns(6)
    cols[0].metric(
        "Confidence",
        f"{final_score:.2f} {assessment['final_confidence_level']}",
        f"{confidence_delta:+.2f} from {initial_score:.2f}",
    )
    transitions = assessment.get("plan_transitions", []) or []
    intermediate = [
        format_identifier(transition["to_mode"])
        for transition in transitions[:-1]
    ]
    if intermediate:
        plan_delta_text = "via " + " → ".join(intermediate)
    else:
        plan_delta_text = (
            f"from {format_identifier(assessment['initial_plan_mode'])}"
        )
    cols[1].metric(
        "Plan",
        format_identifier(assessment["final_plan_mode"]),
        plan_delta_text,
        delta_color="off",
    )
    # Plan width and agent participation are different measurements and are
    # always labelled as such, so a narrowing plan never looks like a
    # contradiction of the agents that informed it.
    initial_width = int(assessment.get("initial_plan_agent_count", initial_agents))
    final_width = int(assessment.get("final_plan_agent_count", final_agents))
    peak_width = int(assessment.get("peak_plan_agent_count", final_width))
    cols[2].metric(
        "Plan width",
        f"{initial_width} → {final_width}",
        f"peak {peak_width}" if peak_width > max(initial_width, final_width)
        else f"{final_width - initial_width:+d} agents",
        delta_color="off",
    )
    readiness = assessment["automation_readiness"]["status"]
    cols[3].metric("Automation readiness", readiness)
    cols[4].metric(
        "Approval",
        str(conceptual.get("Approval state", assessment.get("approval_state", ""))).replace(
            "AWAITING_APPROVAL", "REQUESTED"
        ),
    )
    cols[5].metric("Outcome", conceptual.get("Outcome", "Pending"))


def confidence_chart(repo: StoryRepository, correlation_id: str) -> go.Figure:
    frame = repo.confidence_series(correlation_id)
    figure = px.line(
        frame,
        x="sequence",
        y="confidence",
        markers=True,
        custom_data=["event", "level", "summary"],
    )
    figure.update_traces(
        line={"width": 4},
        marker={"size": 11},
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Confidence: %{y:.3f} %{customdata[1]}<br>"
            "%{customdata[2]}<extra></extra>"
        ),
    )
    figure.update_layout(
        title="Confidence changes as evidence changes",
        xaxis_title="Execution sequence",
        yaxis_title="Operational confidence",
        yaxis_range=[0, 1.05],
        height=390,
        margin={"l": 20, "r": 20, "t": 58, "b": 20},
    )
    threshold = repo.readiness_confidence_threshold()
    figure.add_hline(
        y=threshold,
        line_dash="dash",
        annotation_text=f"Automation-readiness threshold: {threshold:.2f}",
    )
    return figure


def agent_chart(assessment: dict[str, Any]) -> go.Figure:
    frame = pd.DataFrame(
        {
            "stage": ["Initial plan", "Final plan"],
            "agents": [
                int(assessment["initial_agent_count"]),
                int(assessment["final_agent_count"]),
            ],
        }
    )
    figure = px.bar(frame, x="stage", y="agents", text="agents")
    figure.update_traces(textposition="outside")
    figure.update_layout(
        title="Agent participation emerges from required skills",
        xaxis_title="",
        yaxis_title="Reasoning agents",
        height=390,
        yaxis_range=[0, max(frame["agents"].max() + 2, 5)],
        margin={"l": 20, "r": 20, "t": 58, "b": 20},
        showlegend=False,
    )
    return figure


def plan_transition_html(assessment: dict[str, Any], delta: dict[str, Any]) -> str:
    def chips(items: list[str], css_class: str = "") -> str:
        if not items:
            return '<span class="skill-chip">None</span>'
        return "".join(
            f'<span class="skill-chip {css_class}">{safe_text(format_identifier(item))}</span>'
            for item in items
        )

    cancelled_block = ""
    if delta.get("cancelled"):
        cancelled_block = (
            '<div style="margin-top:.55rem;">'
            '<div class="eaios-section-label" style="margin-bottom:.2rem;">'
            "Cancelled before execution</div>"
            + chips(delta["cancelled"], "cancelled")
            + "</div>"
        )

    return f"""
    <div class="eaios-section-label">Adaptive plan revision</div>
    <div style="display:grid;grid-template-columns:1fr 80px 1fr;gap:.75rem;align-items:stretch;">
      <div class="eaios-plan">
        <div class="eaios-plan-title">Initial · {safe_text(format_identifier(assessment['initial_plan_mode']))}</div>
        <div>{chips(delta['initial'])}</div>
        <div style="margin-top:.8rem;opacity:.72;">{assessment['initial_agent_count']} qualified agents selected</div>
      </div>
      <div class="eaios-arrow">→</div>
      <div class="eaios-plan">
        <div class="eaios-plan-title">Final · {safe_text(format_identifier(assessment['final_plan_mode']))}</div>
        <div>{chips(delta['preserved'])}</div>
        <div style="margin-top:.45rem;">{chips(delta['added'], 'added')}</div>
        {cancelled_block}
        <div style="margin-top:.8rem;opacity:.72;">{assessment['final_agent_count']} qualified agents executed</div>
      </div>
    </div>
    """


def render_timeline(events: pd.DataFrame) -> None:
    if events.empty:
        st.info("No execution events were generated for this assessment.")
        return
    def cell(value: Any) -> str:
        # Empty CSV cells arrive as NaN, which is truthy and stringifies to
        # "nan"; plan-level events legitimately have no agent or skill.
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        return str(value).strip()

    for _, row in events.iterrows():
        title = str(row["event_type"]).replace("_", " ").title()
        agent = cell(row.get("agent_name"))
        skill = cell(row.get("skill_id"))
        context = " · ".join(part for part in [agent, format_identifier(skill) if skill else ""] if part)
        with st.expander(f"{int(row['sequence'])}. {title}" + (f" — {context}" if context else "")):
            st.write(row.get("summary", ""))
            before = row.get("confidence_before")
            after = row.get("confidence_after")
            if pd.notna(before) or pd.notna(after):
                st.caption(f"Confidence: {before if pd.notna(before) else '—'} → {after if pd.notna(after) else '—'}")


def render_adaptive_story(
    repo: StoryRepository,
    assessment: dict[str, Any],
    correlation_id: str,
) -> None:
    chart_col, agent_col = st.columns([1.55, 1])
    with chart_col:
        st.plotly_chart(confidence_chart(repo, correlation_id), width="stretch")
    with agent_col:
        st.plotly_chart(agent_chart(assessment), width="stretch")

    delta = repo.plan_delta(correlation_id)
    st.markdown(plan_transition_html(assessment, delta), unsafe_allow_html=True)
    if assessment.get("plan_transitions"):
        st.caption(assessment["plan_transitions"][-1].get("reason", ""))
    else:
        st.caption("Confidence remained stable, so no plan revision was required.")

    st.divider()
    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("Governed execution timeline")
        render_timeline(repo.get_execution_events(correlation_id))
    with right:
        recommendation = assessment.get("recommendation", {})
        st.subheader("Current operational belief")
        st.markdown(
            f"**Leading hypothesis:** `{recommendation.get('leading_hypothesis_id', '')}` — "
            f"{recommendation.get('leading_hypothesis_title', '')}"
        )
        alternatives = recommendation.get("alternative_hypothesis_ids", [])
        st.markdown(
            "**Alternatives retained:** " + (", ".join(f"`{x}`" for x in alternatives) if alternatives else "None")
        )
        st.markdown("**Governed recommendation**")
        st.info(recommendation.get("recommended_action", ""))
        with st.expander("Validation steps"):
            for index, step in enumerate(recommendation.get("validation_steps", []), start=1):
                st.write(f"{index}. {step}")


def render_comparison(repo: StoryRepository, selected: str) -> None:
    labels = repo.assessment_labels()
    ids = list(labels)

    st.subheader("Compare two scenarios")
    st.caption(
        "The engine and the business goal are identical across scenarios. "
        "Evidence changes confidence, confidence changes the required skills, "
        "and the required skills change which agents are selected."
    )

    picker = st.columns(2)
    baseline_id = picker[0].selectbox(
        "Baseline scenario",
        ids,
        index=ids.index(selected) if selected in ids else 0,
        format_func=lambda cid: labels[cid],
        key="comparison_baseline",
    )
    remaining = [cid for cid in ids if cid != baseline_id]
    comparison_id = picker[1].selectbox(
        "Comparison scenario",
        remaining,
        format_func=lambda cid: labels[cid],
        key="comparison_target",
    )

    if baseline_id == comparison_id:
        st.info("Choose two different scenarios to compare.")
        return

    st.dataframe(
        repo.compare(baseline_id, comparison_id),
        hide_index=True,
        width="stretch",
    )

    identities = [repo.scenario_identity(
        repo.get_assessment(cid)["scenario_id"]
    ) for cid in (baseline_id, comparison_id)]
    st.caption(
        " · ".join(
            f"**{identity['short_label']}**: {identity['scenario_category']}"
            for identity in identities
            if identity["scenario_category"]
        )
    )

    paths = st.columns(2)
    for column, correlation_id in zip(paths, (baseline_id, comparison_id)):
        assessment = repo.get_assessment(correlation_id)
        route = " → ".join(
            format_identifier(mode)
            for mode in [assessment["initial_plan_mode"]]
            + [t["to_mode"] for t in assessment.get("plan_transitions", []) or []]
        )
        column.markdown(f"**Plan path**  \n{route}")


def render_scenario_spread(repo: StoryRepository) -> None:
    """Confidence across every scenario, as context for the pair above."""
    rows = []
    for assessment in repo.assessments:
        identity = repo.scenario_identity(assessment["scenario_id"])
        rows.extend(
            [
                {
                    "scenario": identity["short_label"],
                    "stage": "Initial",
                    "confidence": assessment["initial_confidence_score"],
                },
                {
                    "scenario": identity["short_label"],
                    "stage": "Final",
                    "confidence": assessment["final_confidence_score"],
                },
            ]
        )
    figure = px.bar(
        pd.DataFrame(rows),
        x="scenario",
        y="confidence",
        color="stage",
        barmode="group",
        text_auto=".2f",
    )
    figure.update_layout(
        title="Confidence before and after governed execution",
        xaxis_title="",
        yaxis_title="Operational confidence",
        yaxis_range=[0, 1.05],
        height=420,
        margin={"l": 20, "r": 20, "t": 65, "b": 20},
    )
    st.plotly_chart(figure, width="stretch")


def render_evidence(repo: StoryRepository, assessment: dict[str, Any], correlation_id: str) -> None:
    render_vendor_health(repo, correlation_id)
    conflicts = repo.material_conflicts(correlation_id)
    adjudications = {
        row["source_id"]: row for row in repo.conflict_adjudications(correlation_id)
    }
    if conflicts:
        counts = repo.conflict_counts(correlation_id)
        st.subheader("Material knowledge conflict")
        count_cols = st.columns(2)
        count_cols[0].metric("Active material conflicts", counts["active"])
        count_cols[1].metric("Resolved material conflicts", counts["resolved"])
        st.caption(
            "Evidence is never rewritten to match the conclusion. A conflict that "
            "was material when retrieved stays recorded that way; retiring it is a "
            "separate, auditable decision shown alongside."
        )
        for conflict in conflicts:
            reasons = conflict.get("limitation_reasons", []) or []
            reason_html = "".join(f"<li>{safe_text(format_identifier(reason))}</li>" for reason in reasons)
            st.markdown(
                f"""
                <div class="eaios-conflict">
                  <div class="eaios-section-label">Candidate knowledge evaluated — not promoted to truth</div>
                  <h3 style="margin:.25rem 0;">{safe_text(conflict.get('source_id'))} · {safe_text(conflict.get('title'))}</h3>
                  <div class="eaios-kv">
                    <div>Disposition</div><div><b>{safe_text(conflict.get('governance_decision'))}</b></div>
                    <div>Trust</div><div>{safe_text(conflict.get('trust_level'))}</div>
                    <div>Contradicts</div><div>{safe_text(', '.join(conflict.get('contradicts_known_error_ids', [])))}</div>
                    <div>Alternative hypothesis</div><div>{safe_text(conflict.get('alternative_hypothesis_id'))}</div>
                    <div>Independent corroboration</div><div>{safe_text(conflict.get('corroboration_count', 0))}</div>
                  </div>
                  <ul>{reason_html}</ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_adjudication(adjudications.get(conflict.get("source_id")))
        st.info(
            "The article is accepted as evidence that uncertainty exists, but not as confirmed root cause. "
            "That distinction reduces confidence and expands due diligence."
        )
    else:
        st.success("No material knowledge contradiction was detected in this assessment.")

    items = repo.knowledge_items(correlation_id)
    st.subheader("Governed retrieval decisions")
    if items.empty:
        st.caption("The accelerated path did not require broad knowledge retrieval.")
        return

    display = items[
        [
            "source_id",
            "title",
            "source_type",
            "trust",
            "decision",
            "material_contradiction",
            "corroboration_count",
            "reasons",
        ]
    ].rename(
        columns={
            "source_id": "Source",
            "title": "Title",
            "source_type": "Type",
            "trust": "Trust",
            "decision": "Disposition",
            "material_contradiction": "Material conflict",
            "corroboration_count": "Corroboration",
            "reasons": "Evaluation reasons",
        }
    )
    st.dataframe(display, hide_index=True, width="stretch", height=420)

    with st.expander("Evidence-fusion reasoning"):
        st.write(assessment.get("recommendation", {}).get("reasoning_summary", ""))
        uncertainty = assessment.get("recommendation", {}).get("uncertainty_factors", [])
        guardrails = assessment.get("recommendation", {}).get("guardrail_reasons", [])
        st.markdown("**Uncertainty factors**")
        st.write([format_identifier(item) for item in uncertainty])
        st.markdown("**Guardrails**")
        st.write([format_identifier(item) for item in guardrails])


def render_readiness(repo: StoryRepository, assessment: dict[str, Any], correlation_id: str) -> None:
    readiness = assessment["automation_readiness"]
    passed = sum(bool(row.get("passed")) for row in readiness.get("criteria", []))
    total = len(readiness.get("criteria", []))

    left, right = st.columns([1.15, 1])
    with left:
        st.subheader(f"Automation readiness: {readiness['status']}")
        st.progress(passed / total if total else 0, text=f"{passed} of {total} advisory criteria passed")
        st.write(readiness.get("explanation", ""))
        if readiness.get("blockers"):
            st.markdown("**Current blockers**")
            st.write([format_identifier(item) for item in readiness["blockers"]])
    with right:
        st.subheader("Required controls remain active")
        for constraint in readiness.get("required_constraints", []):
            st.write(f"✓ {format_identifier(constraint)}")
        st.warning("V1 is advisory only. Human approval remains enforced regardless of readiness status.")

    criteria = repo.readiness_criteria(correlation_id)
    st.subheader("Readiness decision matrix")
    st.dataframe(criteria.drop(columns=["criterion_id"]), hide_index=True, width="stretch")

    maturation = repo.confidence_maturation.copy()
    maturation["sample_size"] = pd.to_numeric(maturation["sample_size"], errors="coerce")
    maturation["confidence_score"] = pd.to_numeric(maturation["confidence_score"], errors="coerce")
    figure = px.line(
        maturation,
        x="sample_size",
        y="confidence_score",
        markers=True,
        custom_data=["checkpoint", "confidence_level", "drift_status", "automation_readiness"],
    )
    figure.update_traces(
        line={"width": 4},
        marker={"size": 10},
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Confidence: %{y:.3f} %{customdata[1]}<br>"
            "Drift: %{customdata[2]}<br>Readiness: %{customdata[3]}<extra></extra>"
        ),
    )
    figure.update_layout(
        title="Confidence matures through comparable governed outcomes",
        xaxis_title="Comparable executions",
        yaxis_title="Confidence",
        yaxis_range=[0, 1.05],
        height=430,
        margin={"l": 20, "r": 20, "t": 65, "b": 20},
    )
    threshold = repo.readiness_confidence_threshold()
    figure.add_hline(
        y=threshold,
        line_dash="dash",
        annotation_text=f"Automation-readiness threshold: {threshold:.2f}",
    )
    st.plotly_chart(figure, width="stretch")
    st.caption(
        "The dip at 40 outcomes demonstrates that recent failure and recurrence can suspend readiness; "
        "later successful outcomes restore the evidence base. Confidence is necessary, but policy, "
        "risk, reversibility, drift, and contradiction are also required."
    )


def render_servicenow_boundary(
    repo: StoryRepository,
    assessment: dict[str, Any],
    correlation_id: str,
    preview: dict[str, Any],
) -> None:
    conceptual = preview.get("conceptual_values", {})
    payload = preview.get("mapped_servicenow_payload", {})
    metadata = repo.servicenow_record_metadata(correlation_id)
    url = repo.servicenow_record_url(correlation_id)

    st.subheader("ServiceNow remains the operational system of record and control")
    cols = st.columns(4)
    cols[0].metric("Record", metadata.get("number", "Find by correlation ID"))
    cols[1].metric("Approval", str(payload.get("approval", "requested")).title())
    cols[2].metric("Outcome", payload.get("u_outcome", "Pending"))
    cols[3].metric("Safety", conceptual.get("Safety status", assessment["safety_status"]))

    st.markdown(
        """
        <div class="eaios-callout">
          <b>Approval and outcome are separate.</b><br>
          ServiceNow approval records whether a human authorized the proposed action. Operational outcome
          remains Pending until execution later proves Successful, Failed, or Partial.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if url:
        st.link_button("Open the ServiceNow assessment", url, width="content")

    boundary_rows = [
        ("Correlation ID", payload.get("u_correlation_id", correlation_id)),
        ("External observation", payload.get("u_external_observation_id", "")),
        ("Service", payload.get("u_external_service_id", "")),
        ("Strategy", payload.get("u_strategy", "")),
        ("Operational confidence", payload.get("u_operational_confidence", "")),
        ("Initial plan", payload.get("u_initial_plan_mode", assessment["initial_plan_mode"])),
        ("Final plan", payload.get("u_final_plan_mode", assessment["final_plan_mode"])),
        ("Initial agents", payload.get("u_initial_agent_count", assessment["initial_agent_count"])),
        ("Final agents", payload.get("u_final_agent_count", assessment["final_agent_count"])),
        ("Automation readiness", payload.get("u_automation_readiness", readiness_status(assessment))),
        ("Approval", payload.get("approval", "requested")),
        ("Outcome", payload.get("u_outcome", "Pending")),
    ]
    boundary_frame = pd.DataFrame(
        [(field, str(value)) for field, value in boundary_rows],
        columns=["ServiceNow field", "Stored value"],
    )
    st.dataframe(boundary_frame, hide_index=True, width="stretch")

    with st.expander("Mapped ServiceNow payload"):
        st.json(payload)
    with st.expander("Technical mapping status"):
        st.write(
            {
                "mapping_status": preview.get("mapping_status"),
                "mapping_error": preview.get("mapping_error"),
                "live_write_blocked": preview.get("live_write_blocked"),
                "target_table": preview.get("target_table"),
            }
        )


def readiness_status(assessment: dict[str, Any]) -> str:
    return str(assessment.get("automation_readiness", {}).get("status", ""))


def main() -> None:
    inject_css()
    try:
        repo = load_repository()
    except StoryDataError as exc:
        st.error(str(exc))
        st.stop()

    labels = repo.assessment_labels()
    correlation_ids = list(labels)
    default_index = next(
        (index for index, cid in enumerate(correlation_ids) if "CONTRADICTION" in cid),
        0,
    )

    with st.sidebar:
        st.markdown("## EAIOS Story Controls")
        selected = st.selectbox(
            "Scenario",
            correlation_ids,
            index=default_index,
            format_func=lambda cid: labels[cid],
        )
        st.caption("Synthetic enterprise data · Read-only visual layer")
        st.divider()
        st.markdown("**Core claim**")
        st.write(
            "Evidence changes confidence. Confidence changes required skills. "
            "Required skills change the agent orchestration."
        )
        st.divider()
        st.markdown("**V1 safety boundary**")
        st.write("Human approval remains mandatory. No autonomous remediation is executed.")

    assessment = repo.get_assessment(selected)
    preview = repo.get_servicenow_preview(selected)

    transition = (
        f"{assessment['initial_confidence_level']} {assessment['initial_confidence_score']:.2f} → "
        f"{assessment['final_confidence_level']} {assessment['final_confidence_score']:.2f}"
    )
    plan_path = " → ".join(
        format_identifier(mode)
        for mode in [assessment["initial_plan_mode"]]
        + [t["to_mode"] for t in assessment.get("plan_transitions", []) or []]
    )
    st.markdown(
        f"""
        <div class="eaios-hero">
          <div class="eaios-eyebrow">Enterprise AI Operating System · Adaptive operations</div>
          <div class="eaios-title">{safe_text(assessment['scenario_name'])}</div>
          <div class="eaios-subtitle">
            {safe_text(transition)} · {safe_text(plan_path)} ·
            plan width {assessment.get('initial_plan_agent_count', assessment['initial_agent_count'])}
            → {assessment.get('final_plan_agent_count', assessment['final_agent_count'])} ·
            {assessment.get('unique_agents_executed', assessment['final_agent_count'])} agents contributed
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_row(assessment, preview)

    expanded = assessment.get("expanded_during_execution")
    contracted = assessment.get("contracted_during_execution")
    if expanded and contracted:
        callout = (
            "<b>Bidirectional adaptation demonstrated:</b> contradictory knowledge widened the "
            "investigation, then deeper change and dependency evidence retired the alternative "
            "explanation. The plan narrowed again and the unneeded fusion step was cancelled before "
            "it ran &mdash; but confidence did not return to its original level, because recovery is "
            "capped well below what contradiction costs."
        )
    elif expanded:
        callout = (
            "<b>Adaptive behavior demonstrated:</b> credible contradictory knowledge was not promoted "
            "to truth. It increased uncertainty, reduced confidence, preserved completed work, and "
            "expanded the governed skill plan from three to six reasoning agents."
        )
    elif contracted:
        callout = (
            "<b>Converging evidence demonstrated:</b> resolving evidence retired competing hypotheses, "
            "so EAIOS narrowed the governed plan and cancelled work that was no longer justified."
        )
    else:
        callout = (
            "<b>Efficient behavior demonstrated:</b> trusted evidence remained coherent, confidence "
            "stayed high, and EAIOS retained the smallest governed skill plan needed for a "
            "recommendation."
        )
    st.markdown(
        f'<div class="eaios-callout">{callout}</div>',
        unsafe_allow_html=True,
    )

    tabs = st.tabs(
        [
            "Adaptive story",
            "Scenario comparison",
            "Evidence & trust",
            "Automation readiness",
            "ServiceNow control",
        ]
    )
    with tabs[0]:
        render_adaptive_story(repo, assessment, selected)
    with tabs[1]:
        render_comparison(repo, selected)
        st.divider()
        render_scenario_spread(repo)
    with tabs[2]:
        render_evidence(repo, assessment, selected)
    with tabs[3]:
        render_readiness(repo, assessment, selected)
    with tabs[4]:
        render_servicenow_boundary(repo, assessment, selected, preview)

    st.markdown(
        "<div class='eaios-footer'>EAIOS V1 visual demonstration · Synthetic data · ServiceNow is the system of record and approval control.</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
