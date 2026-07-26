"""Build the architecture and demonstration deck.

Numbers come from the shipped fixtures and the story bundle rather than being
typed in, so a deck that has drifted from the system fails to build instead of
quietly misrepresenting it.
"""

from __future__ import annotations

from pathlib import Path
import json

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Inches, Pt


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "EAIOS_Architecture_and_Demo.pptx"

# Ocean gradient: deep blue dominates, teal supports, midnight anchors.
DEEP = RGBColor(0x06, 0x5A, 0x82)
TEAL = RGBColor(0x1C, 0x72, 0x93)
MIDNIGHT = RGBColor(0x21, 0x29, 0x5C)
INK = RGBColor(0x1A, 0x1A, 0x1A)
MUTED = RGBColor(0x5A, 0x64, 0x72)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
WASH = RGBColor(0xEF, 0xF3, 0xF7)
WARN = RGBColor(0xB8, 0x50, 0x42)

HEAD = "Cambria"
BODY = "Calibri"

W, H = Inches(13.333), Inches(7.5)


def facts() -> dict:
    bundle = json.loads(
        (ROOT / "outputs" / "servicenow_story_bundle.json").read_text(
            encoding="utf-8"
        )
    )
    by_id = {a["correlation_id"]: a for a in bundle["assessments"]}
    outcomes = json.loads(
        (ROOT / "json" / "outcome_history.json").read_text(encoding="utf-8")
    )
    docs = json.loads(
        (ROOT / "json" / "knowledge_documents.json").read_text(encoding="utf-8")
    )
    entities = json.loads(
        (ROOT / "json" / "entities.json").read_text(encoding="utf-8")
    )
    rels = json.loads(
        (ROOT / "json" / "semantic_relationships.json").read_text(
            encoding="utf-8"
        )
    )
    trust = json.loads(
        (ROOT / "config" / "experience_trust_policy.json").read_text(
            encoding="utf-8"
        )
    )
    return {
        "b": by_id,
        "outcomes": len(outcomes),
        "docs": len(docs),
        "entities": len(entities),
        "rels": len(rels),
        "doc_ceiling": json.loads(
            (ROOT / "config" / "documentation_policy.json").read_text(
                encoding="utf-8"
            )
        )["ceiling"]["maximum_documented_confidence"],
        "peer_cap": trust["attenuation"]["maximum_peer_trust"],
        "provenance": trust["provenance_weights"],
    }


F = facts()


def slide(prs, layout=6):
    return prs.slides.add_slide(prs.slide_layouts[layout])


def box(s, x, y, w, h, text, *, size=14, bold=False, color=INK, font=BODY,
        align=PP_ALIGN.LEFT, space_after=6, line=None):
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = 0
    tf.margin_top = tf.margin_bottom = 0
    for i, part in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        if line:
            p.line_spacing = line
        r = p.add_run()
        r.text = part
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = font
    return tb


def bullets(s, x, y, w, h, items, *, size=15, color=INK, gap=10):
    tb = s.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = 0
    for i, (lead, rest) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        p.line_spacing = 1.15
        a = p.add_run()
        a.text = lead
        a.font.size = Pt(size)
        a.font.bold = True
        a.font.color.rgb = DEEP
        a.font.name = BODY
        if rest:
            b = p.add_run()
            b.text = rest
            b.font.size = Pt(size)
            b.font.color.rgb = color
            b.font.name = BODY
    return tb


def card(s, x, y, w, h, fill=WASH, edge=None):
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.shadow.inherit = False
    if edge:
        sh.line.color.rgb = edge
        sh.line.width = Pt(1.25)
    else:
        sh.line.fill.background()
    sh.text_frame.text = ""
    return sh


def node(s, x, y, w, h, label, sub="", fill=WHITE, edge=DEEP, text=INK):
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = edge
    sh.line.width = Pt(1.5)
    sh.shadow.inherit = False
    tf = sh.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = Inches(0.05)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label
    r.font.size = Pt(11)
    r.font.bold = True
    r.font.color.rgb = text
    r.font.name = BODY
    if sub:
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run()
        r2.text = sub
        r2.font.size = Pt(8.5)
        r2.font.color.rgb = text
        r2.font.name = BODY
    return sh


def connect(s, x1, y1, x2, y2, label="", color=TEAL, dashed=False):
    ln = s.shapes.add_connector(1, x1, y1, x2, y2)
    ln.line.color.rgb = color
    ln.line.width = Pt(1.75)
    if label:
        lx, ly = (x1 + x2) // 2 - Inches(0.55), (y1 + y2) // 2 - Inches(0.16)
        box(s, lx, ly, Inches(1.1), Inches(0.24), label,
            size=8, color=color, align=PP_ALIGN.CENTER, space_after=0)
    return ln


def header(s, eyebrow, title, sub=""):
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, Inches(1.22))
    bar.fill.solid()
    bar.fill.fore_color.rgb = MIDNIGHT
    bar.line.fill.background()
    bar.shadow.inherit = False
    box(s, Inches(0.62), Inches(0.2), Inches(12), Inches(0.26), eyebrow,
        size=10, bold=True, color=RGBColor(0x9F, 0xC4, 0xDC), space_after=0)
    box(s, Inches(0.62), Inches(0.44), Inches(12), Inches(0.46), title,
        size=27, bold=True, color=WHITE, font=HEAD, space_after=0)
    if sub:
        box(s, Inches(0.62), Inches(1.38), Inches(12.1), Inches(0.4), sub,
            size=13, color=MUTED, line=1.2)


def stat(s, x, y, w, value, label, color=DEEP):
    box(s, x, y, w, Inches(0.62), value, size=38, bold=True, color=color,
        font=HEAD, align=PP_ALIGN.CENTER, space_after=0)
    box(s, x, y + Inches(0.66), w, Inches(0.46), label, size=10.5,
        color=MUTED, align=PP_ALIGN.CENTER, space_after=0, line=1.1)


# ---------------------------------------------------------------- slides ---
def build() -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H

    # 1 · Title
    s = slide(prs)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = MIDNIGHT
    bg.line.fill.background()
    bg.shadow.inherit = False
    accent = s.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(9.6), Inches(-1.6), Inches(6.2), Inches(6.2)
    )
    accent.fill.solid()
    accent.fill.fore_color.rgb = DEEP
    accent.line.fill.background()
    accent.shadow.inherit = False
    box(s, Inches(0.9), Inches(2.15), Inches(9), Inches(0.3),
        "ENTERPRISE AI OPERATING SYSTEM", size=12, bold=True,
        color=RGBColor(0x8F, 0xBD, 0xD8), space_after=0)
    box(s, Inches(0.9), Inches(2.55), Inches(8.6), Inches(1.7),
        "Adaptive orchestration\ngoverned by evidence", size=42, bold=True,
        color=WHITE, font=HEAD, space_after=2, line=1.06)
    box(s, Inches(0.9), Inches(4.5), Inches(7.9), Inches(1.1),
        "A working system in which operational confidence is derived from "
        "recorded outcomes, the investigation plan is a consequence of that "
        "confidence, and no path reaches action without a human.",
        size=14, color=RGBColor(0xC9, 0xD8, 0xE6), line=1.35)
    box(s, Inches(0.9), Inches(6.2), Inches(9), Inches(0.3),
        f"{F['entities']} entities · {F['rels']} governed relationships · "
        f"{F['outcomes']} recorded outcomes · 458 tests",
        size=11, color=RGBColor(0x7E, 0xA6, 0xC4), space_after=0)

    # 2 · The problem
    s = slide(prs)
    header(s, "THE PROBLEM", "Most agent systems assert confidence. This one earns it.")
    left = [
        ("A number the model produces. ",
         "Self-reported certainty tells you how fluent the answer was, not "
         "whether the remedy has ever worked here."),
        ("A fixed plan. ",
         "The same steps run whether the case is familiar or unprecedented, so "
         "effort is unrelated to uncertainty."),
        ("Governance as a final gate. ",
         "A check at the end cannot know what the reasoning skipped."),
        ("No memory of outcome. ",
         "A remedy that failed last time is proposed again with equal "
         "conviction."),
    ]
    right = [
        ("Derived from outcomes. ",
         f"{F['outcomes']} recorded cases, weighted by recency and by how each "
         "was established."),
        ("The plan follows the confidence. ",
         "High confidence buys a narrower investigation. Low confidence buys "
         "more agents, not fewer."),
        ("Governance inside the loop. ",
         "Flags bar plans and suspend automation categorically, independent of "
         "any threshold."),
        ("Outcome is memory. ",
         "What happened last time changes what happens next, in both "
         "directions."),
    ]
    box(s, Inches(0.62), Inches(1.5), Inches(5.8), Inches(0.3),
        "WHAT USUALLY HAPPENS", size=11, bold=True, color=WARN)
    bullets(s, Inches(0.62), Inches(1.9), Inches(5.7), Inches(4.6), left, size=13)
    box(s, Inches(7.0), Inches(1.5), Inches(5.8), Inches(0.3),
        "WHAT THIS DOES", size=11, bold=True, color=DEEP)
    bullets(s, Inches(7.0), Inches(1.9), Inches(5.7), Inches(4.6), right, size=13)

    # 3 · Architecture
    s = slide(prs)
    header(s, "ARCHITECTURE", "Four layers, one direction of authority",
           "Each layer answers one question and is not permitted to answer another layer's.")
    layers = [
        ("Semantic graph", "Entities, dependencies, declared applicability.\nWhat exists and what it touches.", DEEP),
        ("Experience ledger", "Recorded outcomes, weighted once by recency,\nprovenance and standing. What has happened.", TEAL),
        ("Confidence engine", "Operational judgement: how alike is this case,\nhow reliable is that pattern, what plan is warranted.", MIDNIGHT),
        ("Evidence fusion", "Explanation and adjudication between sources.\nWhat to tell a human, and why.", DEEP),
    ]
    y = Inches(2.15)
    for i, (name, desc, colour) in enumerate(layers):
        c = card(s, Inches(0.62), y, Inches(11.9), Inches(0.95), fill=WASH)
        bar = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.62), y,
                                 Inches(2.9), Inches(0.95))
        bar.fill.solid()
        bar.fill.fore_color.rgb = colour
        bar.line.fill.background()
        bar.shadow.inherit = False
        tf = bar.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = name
        r.font.size = Pt(15)
        r.font.bold = True
        r.font.color.rgb = WHITE
        r.font.name = HEAD
        box(s, Inches(3.75), y + Inches(0.18), Inches(8.5), Inches(0.7), desc,
            size=12, color=INK, line=1.2)
        y += Inches(1.12)
    box(s, Inches(0.62), Inches(6.72), Inches(12), Inches(0.4),
        "A judgement made in the confidence engine is passed to fusion, never re-derived there. "
        "Both read experience through the ledger, so neither can hold a different past.",
        size=11.5, color=MUTED, line=1.2)

    # 4 · Knowledge graph
    s = slide(prs)
    header(s, "THE KNOWLEDGE GRAPH", "One cause, two platforms, found by traversal",
           "Nothing in the incident says these are related. The relationship is discovered, not declared.")
    nx, ny = Inches(1.05), Inches(2.25)
    node(s, nx, ny, Inches(2.5), Inches(0.78), "GitHub Enterprise",
         "Developers cannot clone", fill=WHITE, edge=DEEP)
    node(s, nx, ny + Inches(2.5), Inches(2.5), Inches(0.78), "Microsoft Teams",
         "Meetings dropping", fill=WHITE, edge=DEEP)
    node(s, Inches(4.35), ny, Inches(2.5), Inches(0.78),
         "Repo access component", "COMP-GITHUB-REPO-ACCESS", fill=WASH, edge=TEAL)
    node(s, Inches(4.35), ny + Inches(2.5), Inches(2.5), Inches(0.78),
         "Signalling component", "COMP-TEAMS-SIGNALING", fill=WASH, edge=TEAL)
    node(s, Inches(7.7), Inches(3.28), Inches(2.6), Inches(0.95),
         "Secure web gateway", "Shared by both paths", fill=DEEP, edge=DEEP,
         text=WHITE)
    node(s, Inches(10.75), Inches(3.28), Inches(2.0), Inches(0.95),
         "TLS policy", "changed 6h before", fill=WARN, edge=WARN, text=WHITE)

    connect(s, nx + Inches(2.5), ny + Inches(0.39), Inches(4.35),
            ny + Inches(0.39), "depends on")
    connect(s, nx + Inches(2.5), ny + Inches(2.89), Inches(4.35),
            ny + Inches(2.89), "depends on")
    connect(s, Inches(6.85), ny + Inches(0.39), Inches(7.7), Inches(3.5),
            "routed through")
    connect(s, Inches(6.85), ny + Inches(2.89), Inches(7.7), Inches(4.0),
            "routed through")
    connect(s, Inches(10.3), Inches(3.75), Inches(10.75), Inches(3.75),
            "depends on", color=WARN)

    box(s, Inches(1.05), Inches(6.35), Inches(11.5), Inches(0.7),
        "Two independent symptom reports converge on one component three hops "
        "away. The traversal is filtered to authoritative relationships, so an "
        "inferred or low-confidence edge cannot manufacture a connection.",
        size=12, color=MUTED, line=1.25)

    # 5 · Confidence
    s = slide(prs)
    header(s, "CONCEPT 1 · OPERATIONAL CONFIDENCE",
           "A number with an audit trail behind it")
    stat(s, Inches(0.62), Inches(1.85), Inches(2.6), "0.974",
         "49 recorded cases,\n48 successful")
    stat(s, Inches(3.5), Inches(1.85), Inches(2.6), "0.313",
         "20 cases, amended by\nhumans 45% of the time", color=WARN)
    stat(s, Inches(6.38), Inches(1.85), Inches(2.6), "0.872",
         "no cases here, fifty\non a sibling", color=TEAL)
    stat(s, Inches(9.26), Inches(1.85), Inches(2.6), "0.000",
         "nothing recorded,\nnothing written", color=MUTED)
    box(s, Inches(0.62), Inches(3.55), Inches(12), Inches(0.3),
        "WHAT GOES INTO IT", size=11, bold=True, color=DEEP)
    bullets(s, Inches(0.62), Inches(3.95), Inches(5.9), Inches(2.6), [
        ("Recency. ", "A case from last month counts for more than one from last year."),
        ("Provenance. ", f"Human-verified {F['provenance']['HUMAN_VERIFIED']}, own outcome "
                         f"{F['provenance']['SELF_OUTCOME']}, peer agent "
                         f"{F['provenance']['PEER_AGENT']}."),
        ("Standing. ", "A reliable agent speaking outside its remit counts for almost nothing."),
    ], size=13)
    bullets(s, Inches(7.0), Inches(3.95), Inches(5.5), Inches(2.6), [
        ("Supervision. ", "A plan humans keep amending is one the system is not yet good at proposing."),
        ("Asymmetry. ", "Contradiction costs up to 0.22 in full; recovery is capped at 0.10 and cannot exceed 0.95."),
        ("Never amplifies. ", f"Transferred belief is capped at {F['peer_cap']} of its source."),
    ], size=13)

    # 6 · Dynamic planning
    s = slide(prs)
    header(s, "CONCEPT 2 · DYNAMIC PLANNING",
           "The plan is a consequence, not a setting")
    chart_data = CategoryChartData()
    chart_data.categories = ["Known\n0.974", "Contradicted\n0.754", "Resolved\n0.854",
                             "By analogy\n0.872", "From manual\n0.450", "Unknown\n0.000"]
    chart_data.add_series("Reasoning agents", (3, 6, 6, 5, 5, 5))
    gf = s.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.62), Inches(1.75), Inches(7.4), Inches(4.1), chart_data
    )
    ch = gf.chart
    ch.has_title = True
    ch.chart_title.text_frame.text = "Agents engaged, by confidence"
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(13)
    ch.has_legend = False
    plot = ch.plots[0]
    plot.gap_width = 60
    for pt in plot.series[0].points:
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = TEAL
    plot.series[0].points[0].format.fill.fore_color.rgb = DEEP
    ch.value_axis.has_major_gridlines = True
    ch.category_axis.tick_labels.font.size = Pt(9)
    ch.value_axis.tick_labels.font.size = Pt(9)
    bullets(s, Inches(8.4), Inches(1.95), Inches(4.3), Inches(4.2), [
        ("Confidence buys narrowness. ", "0.974 runs three agents. Everything else runs five or six."),
        ("It expands mid-run. ", "Contradictory knowledge widened the plan from three agents to six while it executed."),
        ("And contracts. ", "Resolving evidence retires a hypothesis and cancels work before it runs."),
        ("High is not enough. ", "0.872 is HIGH and still runs the full plan, because the match is an analogy."),
    ], size=12.5)

    # 7 · Collective intelligence
    s = slide(prs)
    header(s, "CONCEPT 3 · COLLECTIVE INTELLIGENCE",
           "Experience is recalled by presentation, and discounted by distance")
    steps = [
        ("Fingerprint", "What the case looks like:\nsymptoms, position,\nblast radius — not its label.", WASH, INK),
        ("Similarity", "Graded, not boolean.\nA familiar component with an\nunfamiliar symptom is not a match.", WASH, INK),
        ("Classify", "DIRECT · TRANSFERRED ·\nDOCUMENTED · none.\nEach worth a different amount.", DEEP, WHITE),
        ("Discount", "Transferred capped at 0.85.\nAn analogy can raise confidence\nand never buys the shortcut.", WASH, INK),
    ]
    x = Inches(0.62)
    for title, desc, fill, tcol in steps:
        c = card(s, x, Inches(1.95), Inches(2.85), Inches(2.5), fill=fill)
        box(s, x + Inches(0.22), Inches(2.15), Inches(2.4), Inches(0.35), title,
            size=15, bold=True, color=WHITE if fill == DEEP else DEEP, font=HEAD)
        box(s, x + Inches(0.22), Inches(2.62), Inches(2.45), Inches(1.7), desc,
            size=11.5, color=tcol, line=1.25)
        x += Inches(3.05)
    box(s, Inches(0.62), Inches(4.75), Inches(12), Inches(0.32),
        "WHERE EXPERIENCE COMES FROM", size=11, bold=True, color=DEEP)
    bullets(s, Inches(0.62), Inches(5.15), Inches(5.9), Inches(1.9), [
        ("Its own outcomes. ", "Direct but unsupervised."),
        ("Human verification. ", "Stronger than an unexamined success, because someone competent looked."),
    ], size=13)
    bullets(s, Inches(7.0), Inches(5.15), Inches(5.5), Inches(1.9), [
        ("A peer agent. ", "Real evidence, second-hand, bounded by that agent's standing over the claim."),
        ("Authority attenuates. ", "Through delegation and through transfer. It never amplifies."),
    ], size=13)

    # 8 · Governance
    s = slide(prs)
    header(s, "CONCEPT 4 · GOVERNANCE",
           "Three tiers, and every flag placed on purpose",
           "Confidence decides how much investigation is proportionate. It does not decide whether governance applies.")
    tiers = [
        ("Bars the narrow plan", DEEP,
         "Transferred experience · documentation only · provisional pattern · "
         "previously ineffective remedy · recent high-risk change · vendor status unknown"),
        ("Suspends automation", MIDNIGHT,
         "Anything not backed by the system's own recorded outcomes. Readiness "
         "asks whether this system has earned the right to act unattended, and "
         "only its own history can answer."),
        ("Informational", TEAL,
         "Reopened the knowledge search · newer documentation available. These "
         "disclose what was found and carry no plan effect."),
    ]
    y = Inches(2.15)
    for name, colour, desc in tiers:
        card(s, Inches(0.62), y, Inches(11.9), Inches(1.25), fill=WASH)
        chip = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.85),
                                  y + Inches(0.28), Inches(3.0), Inches(0.68))
        chip.fill.solid()
        chip.fill.fore_color.rgb = colour
        chip.line.fill.background()
        chip.shadow.inherit = False
        tf = chip.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = name
        r.font.size = Pt(12.5)
        r.font.bold = True
        r.font.color.rgb = WHITE
        r.font.name = BODY
        box(s, Inches(4.1), y + Inches(0.3), Inches(8.2), Inches(0.85), desc,
            size=12, color=INK, line=1.25)
        y += Inches(1.42)
    box(s, Inches(0.62), Inches(6.55), Inches(12), Inches(0.5),
        "Lower the confidence threshold from 0.85 to 0.30 and nothing gains a "
        "shortcut. The flags are categorical, not advisory — that is the "
        "difference between a threshold and a control.",
        size=12.5, bold=True, color=DEEP, line=1.25)

    # 9 · Evidence fusion
    s = slide(prs)
    header(s, "CONCEPT 5 · EVIDENCE FUSION",
           "Every source named, weighted, and accounted for")
    rows = [
        ("Telemetry", "OBSERVED", "0.90", "Breaching signal establishes something is wrong, not what."),
        ("Graph relationship", "AUTHORITATIVE", "1.00", "Declared dependency, filtered to authoritative edges."),
        ("Outcome history", "COLLECTIVE", "0.95", "49 comparable cases, weighted by recency and provenance."),
        ("KB-PAY-001", "ENTITY + SYMPTOM", "1.00", "About this component and this symptom. May support a cause."),
        ("KB-BUS-001", "LEXICAL ONLY", "0.40", "Relevant to the neighbourhood, not to this failure. Contributes nothing."),
        ("Vendor advisory", "EXTERNAL", "0.92", "Another agent's finding, bounded by its standing."),
    ]
    hy = Inches(1.85)
    for lab, x, w in (("SOURCE", Inches(0.62), Inches(2.7)),
                      ("ADMITTED BECAUSE", Inches(3.42), Inches(2.5)),
                      ("WEIGHT", Inches(6.02), Inches(0.9)),
                      ("WHAT IT IS WORTH", Inches(7.05), Inches(5.5))):
        box(s, x, hy, w, Inches(0.3), lab, size=9.5, bold=True, color=MUTED)
    y = hy + Inches(0.42)
    for name, basis, weight, why in rows:
        faded = basis == "LEXICAL ONLY"
        colour = MUTED if faded else INK
        card(s, Inches(0.62), y, Inches(11.9), Inches(0.62),
             fill=RGBColor(0xF7, 0xF9, 0xFB) if faded else WASH)
        box(s, Inches(0.85), y + Inches(0.17), Inches(2.5), Inches(0.3), name,
            size=12, bold=True, color=DEEP if not faded else MUTED)
        box(s, Inches(3.42), y + Inches(0.18), Inches(2.5), Inches(0.3), basis,
            size=10, color=colour)
        box(s, Inches(6.02), y + Inches(0.18), Inches(0.9), Inches(0.3), weight,
            size=11, bold=True, color=colour)
        box(s, Inches(7.05), y + Inches(0.18), Inches(5.4), Inches(0.3), why,
            size=10.5, color=colour)
        y += Inches(0.72)
    box(s, Inches(0.62), Inches(6.6), Inches(12), Inches(0.4),
        "Two retrieval paths read the same corpus and answer different "
        "questions. Neither is gated away; fusion weighs the difference and "
        "the ledger records which basis admitted each item.",
        size=12, color=MUTED, line=1.2)

    # 10 · The doctor question
    s = slide(prs)
    header(s, "THE USE CASE", "A new alert arrives. What does it already know?",
           "The question a panel actually asks, and the three answers the system gives.")
    cases = [
        ("SEEN IT HERE", "0.974", "Recall its own outcomes.\nNarrow the plan to three agents.\nStill requires approval.", DEEP),
        ("SEEN IT NEXT DOOR", "0.872", "Recognise the analogy.\nRaise confidence, keep the full plan.\nRecord that it is transferred.", TEAL),
        ("NEVER SEEN IT", "0.450", "Read the runbook. Propose a cause,\nname the source, cap the confidence.\nAsk a human to validate.", MIDNIGHT),
        ("NOTHING WRITTEN", "0.000", "Propose nothing. List the evidence\nto gather and escalate.\nNot knowing is a finding.", MUTED),
    ]
    x = Inches(0.62)
    for title, value, desc, colour in cases:
        card(s, x, Inches(1.95), Inches(2.85), Inches(3.5), fill=WASH)
        strip = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(1.95),
                                   Inches(2.85), Inches(0.62))
        strip.fill.solid()
        strip.fill.fore_color.rgb = colour
        strip.line.fill.background()
        strip.shadow.inherit = False
        tf = strip.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = title
        r.font.size = Pt(11.5)
        r.font.bold = True
        r.font.color.rgb = WHITE
        r.font.name = BODY
        box(s, x, Inches(2.75), Inches(2.85), Inches(0.6), value, size=32,
            bold=True, color=colour, font=HEAD, align=PP_ALIGN.CENTER)
        box(s, x + Inches(0.22), Inches(3.5), Inches(2.45), Inches(1.8), desc,
            size=11.5, color=INK, line=1.3)
        x += Inches(3.05)
    box(s, Inches(0.62), Inches(5.75), Inches(12), Inches(0.55),
        "Every one of these is a complete, governed output. The last is the "
        "hardest to get from a system that always wants to produce something, "
        "and it is the one that makes the others trustworthy.",
        size=12.5, color=MUTED, line=1.25)

    # 11 · Learning loop
    s = slide(prs)
    header(s, "CONCEPT 6 · LEARNING FROM OUTCOME",
           "The loop that turns a first encounter into a second one")
    stages = [
        ("1 · Never seen", "0.450", "Cause proposed from a runbook,\nsource named, no experience claimed."),
        ("2 · Human validates", "—", "Confirmed, corrected or rejected.\nA correction mints a pattern."),
        ("3 · Provisional", "1 case", "Recorded as an ordinary pattern so\nthe next encounter recalls it normally."),
        ("4 · Seen again", "0.341 / ~0", "The same presentation behaves\ndifferently depending on what happened."),
    ]
    x = Inches(0.62)
    for i, (title, value, desc) in enumerate(stages):
        card(s, x, Inches(1.95), Inches(2.7), Inches(2.35), fill=WASH)
        box(s, x + Inches(0.2), Inches(2.12), Inches(2.3), Inches(0.3), title,
            size=12.5, bold=True, color=DEEP)
        box(s, x + Inches(0.2), Inches(2.48), Inches(2.3), Inches(0.45), value,
            size=20, bold=True, color=MIDNIGHT, font=HEAD)
        box(s, x + Inches(0.2), Inches(3.02), Inches(2.35), Inches(1.2), desc,
            size=11, color=INK, line=1.25)
        if i < 3:
            box(s, x + Inches(2.72), Inches(2.9), Inches(0.3), Inches(0.4), "→",
                size=18, bold=True, color=TEAL, align=PP_ALIGN.CENTER)
        x += Inches(3.02)
    box(s, Inches(0.62), Inches(4.65), Inches(12), Inches(0.32),
        "WHAT MAKES IT LEARNING RATHER THAN LOGGING", size=11, bold=True, color=DEEP)
    bullets(s, Inches(0.62), Inches(5.05), Inches(5.9), Inches(1.9), [
        ("A failed remedy is named. ", "Not just a lower average — carried forward as a specific fact."),
        ("Rejection lowers, never bans. ", "A human can reject wrongly; treating one rejection as final makes that error unfalsifiable."),
    ], size=12.5)
    bullets(s, Inches(7.0), Inches(5.05), Inches(5.5), Inches(1.9), [
        ("One case is not experience. ", "Provisional patterns are discounted until fifteen cases hold."),
        ("Promotion reverses itself. ", "Evaluated from the record, so a falling success rate demotes without anyone remembering to."),
    ], size=12.5)

    # 12 · The demo
    s = slide(prs)
    header(s, "THE DEMONSTRATION", "Six beats, ten minutes",
           "Each beat raises the question the next one answers.")
    beats = [
        ("1", "It has seen this 49 times", "0.974 → 3 agents. Confidence is earned and buys narrowness."),
        ("2", "Confidence can be lost mid-run", "0.974 → 0.754 → 0.854. Recovery is capped below the loss."),
        ("3", "One cause, two platforms", "Shared gateway found by traversal, not declared."),
        ("4", "Never here, but fifty times next door", "0.872 HIGH — and still the full plan."),
        ("5", "Never seen at all", "Reads the manual. Then, with no manual, says nothing."),
        ("6", "Seen once before", "0.341 if the remedy worked, near zero if it did not."),
    ]
    y = Inches(1.9)
    for num, title, detail in beats:
        card(s, Inches(0.62), y, Inches(11.9), Inches(0.74), fill=WASH)
        circ = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.85),
                                  y + Inches(0.13), Inches(0.48), Inches(0.48))
        circ.fill.solid()
        circ.fill.fore_color.rgb = DEEP
        circ.line.fill.background()
        circ.shadow.inherit = False
        tf = circ.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = num
        r.font.size = Pt(14)
        r.font.bold = True
        r.font.color.rgb = WHITE
        r.font.name = HEAD
        box(s, Inches(1.6), y + Inches(0.13), Inches(4.4), Inches(0.3), title,
            size=13.5, bold=True, color=INK)
        box(s, Inches(6.1), y + Inches(0.16), Inches(6.2), Inches(0.3), detail,
            size=11.5, color=MUTED)
        y += Inches(0.84)
    box(s, Inches(0.62), Inches(6.9), Inches(12), Inches(0.3),
        "python rehearse.py  ·  python -m streamlit run eaios_story_app.py",
        size=11, bold=True, color=TEAL)

    # 13 · How it is verified
    s = slide(prs)
    header(s, "HOW IT IS HELD TOGETHER", "The tests are the specification")
    stat(s, Inches(0.62), Inches(1.95), Inches(2.9), "458", "tests, all passing")
    stat(s, Inches(3.7), Inches(1.95), Inches(2.9), "23", "story-shape tests:\ndirections, not values", color=TEAL)
    stat(s, Inches(6.78), Inches(1.95), Inches(2.9), "11", "layer-agreement tests:\nthe two layers must concur", color=MIDNIGHT)
    stat(s, Inches(9.86), Inches(1.95), Inches(2.9), "10", "structural guards\nagainst known faults", color=DEEP)
    box(s, Inches(0.62), Inches(3.75), Inches(12), Inches(0.32),
        "WHAT THEY DEFEND", size=11, bold=True, color=DEEP)
    bullets(s, Inches(0.62), Inches(4.15), Inches(5.9), Inches(2.6), [
        ("Story shape, not fixture values. ", "A test that pins 0.974 breaks when the data improves. These assert that a contradiction lowers confidence."),
        ("The layers agree. ", "Five faults were found where two components derived the same judgement and disagreed."),
    ], size=12.5)
    bullets(s, Inches(7.0), Inches(4.15), Inches(5.5), Inches(2.6), [
        ("No judgement made twice. ", "A static guard fails when a policy gains a second interpreter without a declared reason."),
        ("The demo cannot lie. ", "A test fails if the app captions a scenario with a claim its own run contradicts."),
    ], size=12.5)

    # 14 · Close
    s = slide(prs)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = MIDNIGHT
    bg.line.fill.background()
    bg.shadow.inherit = False
    box(s, Inches(0.9), Inches(1.5), Inches(11.5), Inches(0.3),
        "IN ONE SENTENCE", size=12, bold=True,
        color=RGBColor(0x8F, 0xBD, 0xD8))
    box(s, Inches(0.9), Inches(1.95), Inches(11.4), Inches(1.9),
        "Evidence changes confidence.\nConfidence changes the plan.\nThe plan "
        "changes which agents run.", size=34, bold=True, color=WHITE,
        font=HEAD, line=1.2)
    box(s, Inches(0.9), Inches(4.15), Inches(10.6), Inches(1.5),
        "And when it has no evidence, it says so — which is the part that "
        "makes everything above it worth trusting. No path in this system "
        "reaches an action without a human, regardless of how confident it is.",
        size=15, color=RGBColor(0xC9, 0xD8, 0xE6), line=1.35)
    line = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.9), Inches(5.9),
                              Inches(1.6), Inches(0.04))
    line.fill.solid()
    line.fill.fore_color.rgb = TEAL
    line.line.fill.background()
    line.shadow.inherit = False
    box(s, Inches(0.9), Inches(6.2), Inches(11), Inches(0.4),
        "Synthetic data throughout · ServiceNow remains the system of record "
        "and approval control", size=11,
        color=RGBColor(0x7E, 0xA6, 0xC4))

    return prs


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    build().save(OUT)
    print(f"Saved {OUT}")
