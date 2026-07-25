from pathlib import Path

from eaios_story_data import StoryRepository


BASE_DIR = Path(__file__).resolve().parent


def test_repository_loads_two_assessments() -> None:
    repo = StoryRepository.load(BASE_DIR)
    assert len(repo.assessments) == 2
    assert "EAIOS-DEMO-CONTRADICTION-001" in repo.assessment_labels()


def test_contradiction_scenario_erodes_confidence_and_expands() -> None:
    repo = StoryRepository.load(BASE_DIR)
    assessment = repo.get_assessment("EAIOS-DEMO-CONTRADICTION-001")
    assert assessment["initial_confidence_score"] == 0.99
    assert assessment["final_confidence_score"] == 0.77
    assert assessment["expanded_during_execution"] is True
    assert assessment["initial_agent_count"] == 3
    assert assessment["final_agent_count"] == 6


def test_plan_delta_preserves_and_adds_skills() -> None:
    repo = StoryRepository.load(BASE_DIR)
    delta = repo.plan_delta("EAIOS-DEMO-CONTRADICTION-001")
    assert "semantic_context" in delta["preserved"]
    assert "due_diligence_validation" in delta["preserved"]
    assert "governed_knowledge_retrieval" in delta["added"]
    assert "evidence_fusion_recommendation" in delta["added"]


def test_material_contradiction_is_accepted_with_limitations() -> None:
    repo = StoryRepository.load(BASE_DIR)
    conflicts = repo.material_conflicts("EAIOS-DEMO-CONTRADICTION-001")
    assert len(conflicts) == 1
    assert conflicts[0]["source_id"] == "KB-CONTRADICT-001"
    assert conflicts[0]["governance_decision"] == "ACCEPTED_WITH_LIMITATIONS"


def test_readiness_is_suspended_with_three_blocked_criteria() -> None:
    repo = StoryRepository.load(BASE_DIR)
    assessment = repo.get_assessment("EAIOS-DEMO-CONTRADICTION-001")
    criteria = repo.readiness_criteria("EAIOS-DEMO-CONTRADICTION-001")
    assert assessment["automation_readiness"]["status"] == "SUSPENDED"
    assert int((criteria["status"] == "BLOCKED").sum()) == 3


def test_servicenow_boundary_preserves_approval_outcome_separation() -> None:
    repo = StoryRepository.load(BASE_DIR)
    preview = repo.get_servicenow_preview("EAIOS-DEMO-CONTRADICTION-001")
    payload = preview["mapped_servicenow_payload"]
    assert payload["approval"] == "requested"
    assert payload["u_outcome"] == "Pending"
    assert preview["mapping_error"] is None
    assert preview["live_write_blocked"] is False
