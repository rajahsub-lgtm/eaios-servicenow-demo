from pathlib import Path

from eaios_story_data import StoryRepository


base_dir = Path(__file__).resolve().parent
repo = StoryRepository.load(base_dir)

for assessment in repo.assessments:
    cid = assessment["correlation_id"]
    assert not repo.confidence_series(cid).empty
    assert repo.get_servicenow_preview(cid)

print("PASS: visual-story data loaded for all assessments.")
print("Scenarios:")
for cid, label in repo.assessment_labels().items():
    print(f"- {cid}: {label}")
