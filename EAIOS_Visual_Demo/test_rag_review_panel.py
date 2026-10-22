import json
import pytest
from rag_review_panel import load_payment_review, RagArtifactError


def save(tmp_path, scenario="SCN-PAY-001", cutoff="2026-07-14 14:50:00"):
    folder = tmp_path / "lab_evals"
    folder.mkdir()
    context = dict(scenario_id=scenario, incident_time="2026-07-14 14:50:00", telemetry=[dict(scenario_id=scenario, as_of=cutoff, latest_readings=[])], accepted_knowledge=[], conditional_knowledge=[dict(chunk_id="KB-X", limitation_reasons=["NO_INDEPENDENT_CORROBORATION"])], structured_records=[])
    (folder / "payment_rag_context.json").write_text(json.dumps(context))
    (folder / "payment_rag_result_v1.json").write_text(json.dumps(dict(brief="Test analysis", stop_reason="end_turn")))


def test_missing_artifacts(tmp_path):
    assert load_payment_review(tmp_path, "SCN-PAY-001") is None


def test_different_dashboard_scenario_never_loads_payment(tmp_path):
    save(tmp_path)
    assert load_payment_review(tmp_path, "SCN-PAY-CONTRADICT-001") is None


def test_preserves_limitations(tmp_path):
    save(tmp_path)
    context, result = load_payment_review(tmp_path, "SCN-PAY-001")
    assert context["conditional_knowledge"][0]["limitation_reasons"] == ["NO_INDEPENDENT_CORROBORATION"]


@pytest.mark.parametrize("scenario,cutoff", [("WRONG", "2026-07-14 14:50:00"), ("SCN-PAY-001", "2026-07-15 14:50:00")])
def test_rejects_wrong_identity_or_cutoff(tmp_path, scenario, cutoff):
    save(tmp_path, scenario, cutoff)
    with pytest.raises(RagArtifactError):
        load_payment_review(tmp_path, "SCN-PAY-001")


def test_malformed_json(tmp_path):
    save(tmp_path)
    (tmp_path / "lab_evals/payment_rag_result_v1.json").write_text("{")
    with pytest.raises(RagArtifactError):
        load_payment_review(tmp_path, "SCN-PAY-001")


def test_populated_panel_renders(tmp_path):
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    save(tmp_path)
    script = tmp_path / "panel_test.py"
    script.write_text(f"import sys\nfrom pathlib import Path\nsys.path.insert(0, {str(Path(__file__).parent)!r})\nfrom rag_review_panel import render_rag_review\nrender_rag_review(Path({str(tmp_path)!r}), 'SCN-PAY-001')\n")
    app = AppTest.from_file(str(script)).run()
    assert not app.exception
    assert any("Test analysis" in item.value for item in app.markdown)
    assert any("unverified" in item.value for item in app.warning)
