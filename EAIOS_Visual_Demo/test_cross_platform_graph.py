"""Shared-dependency discovery must be earned by traversal.

The value of the cross-platform story rests entirely on the shared cause
being found rather than written down. These tests start from the two
symptoms and never name the gateway on the way in.
"""

from pathlib import Path
import json
import unittest

from graph_engine import SemanticGraph


ROOT = Path(__file__).resolve().parent
JSON_DIR = ROOT / "json"

# Edges that mean "cannot function without". Deliberately excludes SUPPORTS
# and CONTRIBUTES_TO, which point at consumers rather than dependencies.
DEPENDENCY_PREDICATES = {
    "DEPENDS_ON",
    "ROUTED_THROUGH",
    "HOSTED_ON",
    "AUTHENTICATES_WITH",
}

GITHUB_SYMPTOM = "COMP-GITHUB-REPO-ACCESS"
TEAMS_SYMPTOM = "COMP-TEAMS-SIGNALING"
SYMPTOMS = [GITHUB_SYMPTOM, TEAMS_SYMPTOM]


def graph() -> SemanticGraph:
    return SemanticGraph.from_json_directory(JSON_DIR)


def discover(g: SemanticGraph, **overrides):
    kwargs = {
        "max_hops": 3,
        "direction": "out",
        "predicates": DEPENDENCY_PREDICATES,
        "minimum_confidence": 0.5,
        "allowed_authorities": {"AUTHORITATIVE"},
    }
    kwargs.update(overrides)
    return g.shared_dependencies(SYMPTOMS, **kwargs)


class SharedDependencyDiscoveryTests(unittest.TestCase):
    def test_gateway_is_discovered_from_the_two_symptoms_alone(self):
        found = discover(graph())
        self.assertTrue(found, "no shared dependency discovered")
        self.assertEqual(found[0].entity_id, "COMP-SECURE-WEB-GATEWAY")

    def test_discovery_ranks_the_nearest_dependency_first(self):
        found = discover(graph())
        ids = [item.entity_id for item in found]
        self.assertEqual(
            ids[:2],
            ["COMP-SECURE-WEB-GATEWAY", "COMP-GATEWAY-TLS-POLICY"],
        )
        self.assertLess(found[0].deepest_hop_count, found[1].deepest_hop_count)

    def test_each_symptom_contributes_its_own_evidenced_path(self):
        top = discover(graph())[0]
        self.assertEqual(set(top.paths), set(SYMPTOMS))
        for source, path in top.paths.items():
            self.assertTrue(path, f"{source} reached the gateway with no steps")
            self.assertEqual(path[-1].to_entity_id, "COMP-SECURE-WEB-GATEWAY")
            for step in path:
                self.assertEqual(step.relationship.authority, "AUTHORITATIVE")

    def test_platforms_are_not_directly_connected_to_each_other(self):
        """The link is the shared dependency, not a shortcut between platforms."""
        g = graph()
        reachable = g.reachable_paths(
            GITHUB_SYMPTOM,
            max_hops=3,
            direction="out",
            predicates=DEPENDENCY_PREDICATES,
        )
        self.assertNotIn(TEAMS_SYMPTOM, reachable)


class TraversalGovernanceTests(unittest.TestCase):
    def test_a_confidence_floor_above_the_weakest_edge_severs_discovery(self):
        found = discover(graph(), minimum_confidence=0.95)
        # The Teams route carries 0.94, so the platforms no longer converge.
        self.assertEqual(found, [])

    def test_unauthoritative_traversal_finds_nothing(self):
        found = discover(graph(), allowed_authorities={"INFERRED"})
        self.assertEqual(found, [])

    def test_hop_budget_bounds_the_search(self):
        shallow = discover(graph(), max_hops=1)
        ids = [item.entity_id for item in shallow]
        self.assertIn("COMP-SECURE-WEB-GATEWAY", ids)
        self.assertNotIn("COMP-GATEWAY-TLS-POLICY", ids)

    def test_consumer_edges_do_not_count_as_shared_dependencies(self):
        """Both platforms serve one business outcome; that is not a cause."""
        g = graph()
        as_dependency = {item.entity_id for item in discover(g)}
        self.assertNotIn("BO-PRODUCTIVITY", as_dependency)

        # Traversing consumer edges instead does reach it, which is why the
        # predicate set has to be chosen deliberately.
        as_consumer = g.shared_dependencies(
            ["AS-GITHUB-ENTERPRISE", "AS-TEAMS"],
            max_hops=3,
            direction="out",
            predicates={"SUPPORTS", "CONTRIBUTES_TO"},
            allowed_authorities={"AUTHORITATIVE"},
        )
        self.assertIn(
            "BO-PRODUCTIVITY",
            {item.entity_id for item in as_consumer},
        )

    def test_discovery_requires_at_least_two_starting_points(self):
        with self.assertRaises(ValueError):
            graph().shared_dependencies([GITHUB_SYMPTOM])


class ChangeCorrelationTests(unittest.TestCase):
    def test_recent_change_is_reachable_from_the_discovered_dependency(self):
        g = graph()
        found = discover(g)
        changes = []
        for item in found:
            for step in g.iter_neighbors(
                item.entity_id, direction="in", predicates={"MODIFIES"}
            ):
                changes.append(step.to_entity_id)
        self.assertIn("CHG-GATEWAY-001", changes)

    def test_the_change_is_recent_and_high_risk(self):
        rows = json.loads((JSON_DIR / "changes.json").read_text(encoding="utf-8"))
        change = next(r for r in rows if r["change_id"] == "CHG-GATEWAY-001")
        self.assertTrue(change["is_recent"])
        self.assertEqual(change["risk"], "High")
        self.assertEqual(change["entity_id"], "COMP-GATEWAY-TLS-POLICY")


class RelationshipProvenanceTests(unittest.TestCase):
    def test_new_edges_carry_authority_confidence_and_provenance(self):
        rows = json.loads(
            (JSON_DIR / "semantic_relationships.json").read_text(encoding="utf-8")
        )
        new_subjects = {
            "AS-GITHUB-ENTERPRISE", "AS-TEAMS", "COMP-GITHUB-REPO-ACCESS",
            "COMP-TEAMS-SIGNALING", "COMP-SECURE-WEB-GATEWAY",
            "CAP-ENG-DELIVERY", "CAP-COLLABORATION", "CHG-GATEWAY-001",
        }
        subject_rows = [r for r in rows if r["subject_entity_id"] in new_subjects]
        self.assertTrue(subject_rows)
        for row in subject_rows:
            with self.subTest(relationship=row["relationship_id"]):
                self.assertIn(row["relationship_authority"], {"AUTHORITATIVE", "OBSERVED", "INFERRED"})
                self.assertGreater(float(row["confidence"]), 0.0)
                self.assertTrue(row["provenance"].strip())
                self.assertEqual(row["status"], "ACTIVE")
                self.assertEqual(row["data_classification"], "SYNTHETIC")

    def test_new_entities_are_marked_synthetic(self):
        rows = json.loads((JSON_DIR / "entities.json").read_text(encoding="utf-8"))
        for entity_id in (
            "AS-GITHUB-ENTERPRISE", "COMP-GITHUB-REPO-ACCESS", "AS-TEAMS",
            "COMP-TEAMS-SIGNALING", "COMP-SECURE-WEB-GATEWAY",
            "COMP-GATEWAY-TLS-POLICY", "CAP-ENG-DELIVERY",
            "CAP-COLLABORATION", "BO-PRODUCTIVITY",
        ):
            with self.subTest(entity=entity_id):
                row = next(r for r in rows if r["entity_id"] == entity_id)
                self.assertEqual(row["data_classification"], "SYNTHETIC")
                self.assertEqual(row["status"], "ACTIVE")


class ExistingGraphUnaffectedTests(unittest.TestCase):
    def test_payment_scenario_entities_are_untouched(self):
        g = graph()
        for entity_id in ("COMP-PAY-CONNECTOR", "AS-ORDER-MGMT", "BO-APP-HEALTH"):
            self.assertIn(entity_id, g.entities)

    def test_payment_component_shares_no_dependency_with_the_new_platforms(self):
        found = graph().shared_dependencies(
            ["COMP-PAY-CONNECTOR", GITHUB_SYMPTOM],
            max_hops=3,
            direction="out",
            predicates=DEPENDENCY_PREDICATES,
            allowed_authorities={"AUTHORITATIVE"},
        )
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
