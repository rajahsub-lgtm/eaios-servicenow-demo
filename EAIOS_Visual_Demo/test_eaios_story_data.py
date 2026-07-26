from pathlib import Path

from eaios_story_data import StoryRepository


BASE_DIR = Path(__file__).resolve().parent


def test_repository_loads_every_demonstration_assessment() -> None:
    repo = StoryRepository.load(BASE_DIR)
    labels = repo.assessment_labels()
    # The seven beats of the demonstration arc, in the order a panel meets
    # them. The count is asserted through the set rather than separately, so
    # adding a beat cannot pass by updating a number and forgetting the story.
    assert list(labels) == [
        "EAIOS-DEMO-STABLE-001",
        "EAIOS-DEMO-CONTRADICTION-001",
        "EAIOS-DEMO-RESOLVED-001",
        "EAIOS-DEMO-CROSS-GATEWAY-001",
        "EAIOS-DEMO-TRANSFERRED-001",
        "EAIOS-DEMO-UNSEEN-001",
        "EAIOS-DEMO-UNDOCUMENTED-001",
    ]
    assert len(repo.assessments) == len(labels)


def test_each_scenario_gets_a_distinct_label() -> None:
    repo = StoryRepository.load(BASE_DIR)
    labels = repo.assessment_labels()
    assert len(set(labels.values())) == len(labels)
    assert labels["EAIOS-DEMO-RESOLVED-001"] == (
        "Payment connector — contradiction resolved"
    )


def test_resolved_scenario_cancels_the_fusion_step() -> None:
    repo = StoryRepository.load(BASE_DIR)
    delta = repo.plan_delta("EAIOS-DEMO-RESOLVED-001")
    assert "evidence_fusion_recommendation" in delta["cancelled"]
    assert delta["directions"] == ["EXPANSION", "CONTRACTION"]


def test_scenarios_without_revisions_report_no_cancellations() -> None:
    repo = StoryRepository.load(BASE_DIR)
    assert repo.plan_delta("EAIOS-DEMO-STABLE-001")["cancelled"] == []


def test_contradiction_scenario_erodes_confidence_and_expands() -> None:
    repo = StoryRepository.load(BASE_DIR)
    assessment = repo.get_assessment("EAIOS-DEMO-CONTRADICTION-001")
    assert (
        assessment["final_confidence_score"]
        < assessment["initial_confidence_score"]
    )
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
