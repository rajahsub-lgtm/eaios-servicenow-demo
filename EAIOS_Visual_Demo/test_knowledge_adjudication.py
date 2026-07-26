"""Two paths read the same corpus; fusion decides what each is worth.

`knowledge_retrieval_agent` finds material a human might want to read, by
lexical relevance to the graph neighbourhood. `documented_reasoning` asks the
narrower question of whether a document is about this component and this
symptom. Neither is wrong. They answer different questions, and the evidence
ledger was quoting the first as though it had answered the second — a payment
knowledge base article arrived as SUPPORTS at reliability 1.0 for a
search-indexer incident.

Neither path is gated away upstream. Both reach the ledger labelled with the
basis that admitted them, and fusion weighs the difference. Adjudicating
between sources of unequal reliability is what the contribution ledger is for.
"""

from pathlib import Path
import unittest

from evidence_fusion_agent import EvidenceFusionAgent


ROOT = Path(__file__).resolve().parent
JSON = ROOT / "json"

_cache: dict = {}


def ledger(scenario_id: str):
    if scenario_id not in _cache:
        _cache[scenario_id] = EvidenceFusionAgent(JSON).analyze(
            scenario_id
        ).evidence_ledger
    return _cache[scenario_id]


def entry(scenario_id: str, evidence_id: str):
    return next(
        row for row in ledger(scenario_id) if row.evidence_id == evidence_id
    )


class EveryItemStatesItsBasisTests(unittest.TestCase):
    def test_no_knowledge_item_is_unassessed(self):
        for scenario_id in ("SCN-PAY-001", "SCN-QUEUE-001"):
            for row in ledger(scenario_id):
                if row.evidence_type in {"KB", "RUNBOOK", "PIR", "WIKI"}:
                    with self.subTest(scenario=scenario_id, item=row.evidence_id):
                        self.assertNotEqual(row.eligibility_basis, "NOT_ASSESSED")


class OnlyRelevantMaterialSupportsACauseTests(unittest.TestCase):
    def test_matched_material_supports(self):
        row = entry("SCN-PAY-001", "KB-PAY-001")
        self.assertEqual(row.eligibility_basis, "ENTITY_AND_SYMPTOM_MATCHED")
        self.assertEqual(row.role, "SUPPORTS")
        self.assertGreater(row.contribution, 0.0)

    def test_lexically_relevant_material_contributes_nothing(self):
        """It used to arrive as SUPPORTS at reliability 1.0."""
        row = entry("SCN-PAY-001", "KB-BUS-001")
        self.assertEqual(row.eligibility_basis, "LEXICAL_RELEVANCE_ONLY")
        self.assertEqual(row.role, "CONTEXT")
        self.assertEqual(row.contribution, 0.0)
        self.assertLess(row.reliability, 1.0)

    def test_it_is_still_surfaced_rather_than_gated_away(self):
        """Material that cannot support a cause can still prompt a useful
        human thought. Removing it would be cheaper and worse."""
        surfaced = {row.evidence_id for row in ledger("SCN-PAY-001")}
        self.assertIn("KB-BUS-001", surfaced)
        self.assertIn("KB-DB-003", surfaced)

    def test_the_rationale_says_why_it_counted_nothing(self):
        row = entry("SCN-PAY-001", "KB-BUS-001")
        self.assertIn("not about this component", row.rationale)
        self.assertIn("contributes nothing", row.rationale)

    def test_a_supporting_item_states_its_symptom_coverage(self):
        self.assertIn(
            "presenting symptoms", entry("SCN-PAY-001", "KB-PAY-001").rationale
        )


class TheDocumentedPathIsLabelledTooTests(unittest.TestCase):
    def test_a_proposal_records_the_basis_that_admitted_it(self):
        row = entry("SCN-NOVEL-INDEX-001", "RB-SEARCH-001")
        self.assertEqual(row.eligibility_basis, "ENTITY_AND_SYMPTOM_MATCHED")
        self.assertEqual(row.role, "PROPOSES_CAUSE")


class TheRuleIsNotDuplicatedTests(unittest.TestCase):
    def test_fusion_asks_the_reasoner_rather_than_deciding_again(self):
        """A second copy of the eligibility rule is the fault this whole
        correction is about."""
        source = (ROOT / "evidence_fusion_agent.py").read_text(encoding="utf-8")
        self.assertIn("self.documentation.eligibility_of", source)
        self.assertNotIn("minimum_symptom_coverage", source)


if __name__ == "__main__":
    unittest.main()
