from pathlib import Path
import unittest

from knowledge_retrieval_agent import KnowledgeRetrievalAgent

ROOT = Path(__file__).resolve().parent


class KnowledgeRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = KnowledgeRetrievalAgent(ROOT / "json")

    def test_payment_top_knowledge_is_payment_connector_article(self):
        result = self.agent.retrieve("SCN-PAY-001")
        self.assertEqual(result.accepted_free_text[0].source_id, "KB-PAY-001")
        ids = {c.source_id for c in result.accepted_free_text}
        self.assertIn("PIR-PAY-003", ids)
        self.assertIn("RUN-PAY-002", ids)

    def test_stale_payment_article_is_rejected(self):
        result = self.agent.retrieve("SCN-PAY-001")
        rejected = {c.source_id: c for c in result.rejected_candidates}
        self.assertIn("KB-LEGACY-PAY-009", rejected)
        self.assertIn("TRUST_STALE", rejected["KB-LEGACY-PAY-009"].rejection_reasons)
        self.assertIn("STALE_OVER_180_DAYS", rejected["KB-LEGACY-PAY-009"].rejection_reasons)

    def test_queue_top_knowledge_and_unsafe_wiki_rejection(self):
        result = self.agent.retrieve("SCN-QUEUE-001")
        self.assertEqual(result.accepted_free_text[0].source_id, "KB-QUEUE-002")
        rejected = {c.source_id: c for c in result.rejected_candidates}
        wiki = rejected["WIKI-QUEUE-011"]
        self.assertIn("TRUST_UNTRUSTED", wiki.rejection_reasons)
        self.assertIn("CONTENT_SAFETY_UNSAFE_INSTRUCTION", wiki.rejection_reasons)
        self.assertIn("SUSPICIOUS_INSTRUCTION_PATTERN", wiki.rejection_reasons)

    def test_structured_records_are_separated_from_free_text(self):
        result = self.agent.retrieve("SCN-PAY-001")
        self.assertTrue(result.accepted_structured_records)
        self.assertTrue(all(
            c.evidence_class == "STRUCTURED_ENTERPRISE_RECORD"
            for c in result.accepted_structured_records
        ))
        self.assertTrue(all(
            c.evidence_class == "FREE_TEXT_KNOWLEDGE"
            for c in result.accepted_free_text
        ))

    def test_future_queue_records_are_rejected(self):
        result = self.agent.retrieve("SCN-QUEUE-001")
        rejected = {c.source_id: c for c in result.rejected_candidates}
        self.assertIn("STRUCTURED_RECORD_NOT_YET_AVAILABLE", rejected["INC-QUEUE-005"].rejection_reasons)
        self.assertIn("STRUCTURED_RECORD_NOT_YET_AVAILABLE", rejected["PRB-ACC-004"].rejection_reasons)

    def test_payment_retrieval_does_not_accept_queue_knowledge(self):
        result = self.agent.retrieve("SCN-PAY-001")
        accepted = {c.source_id for c in result.accepted_free_text}
        self.assertNotIn("KB-QUEUE-002", accepted)
        self.assertNotIn("RUN-QUEUE-003", accepted)


if __name__ == "__main__":
    unittest.main()
