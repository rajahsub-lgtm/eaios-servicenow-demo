from pathlib import Path
import unittest
from graph_engine import SemanticGraph
from demo_graph_reasoning import payment_business_impact_path, payment_knowledge_path, queue_blast_radius_paths

class GraphReasoningTests(unittest.TestCase):
    def test_all_relationship_endpoints_exist(self):
        # Loading is itself the check: the constructor rejects any edge whose
        # subject or object is missing. Asserted explicitly here so the test
        # matches its name, and without a fixed count that would break every
        # time the graph legitimately grows.
        graph = SemanticGraph.from_json_directory(Path(__file__).parent / "json")
        self.assertTrue(graph.relationships)
        for relationship in graph.relationships.values():
            self.assertIn(relationship.subject_entity_id, graph.entities)
            self.assertIn(relationship.object_entity_id, graph.entities)

    def test_payment_business_path_reaches_checkout_and_outcome(self):
        path = payment_business_impact_path()
        self.assertEqual([step.to_entity_id for step in path], [
            "COMP-PAY-CONNECTOR", "AS-ORDER-MGMT", "BS-DIGITAL-COMMERCE", "CAP-CHECKOUT", "BO-APP-HEALTH"
        ])

    def test_payment_known_error_is_applicable(self):
        known_errors = {step.to_entity_id for step in payment_knowledge_path()}
        self.assertIn("KE-PAY-001", known_errors)

    def test_queue_blast_radius_reaches_expected_capabilities(self):
        capabilities = {path[-1].to_entity_id for path in queue_blast_radius_paths()}
        self.assertEqual(capabilities, {"CAP-BILLING", "CAP-RECON", "CAP-FRAUD"})

if __name__ == "__main__":
    unittest.main()
