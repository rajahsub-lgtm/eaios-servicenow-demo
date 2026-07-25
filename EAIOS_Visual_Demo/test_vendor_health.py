"""Vendor evidence is a separate kind of truth.

A vendor can report on its own services and nothing else. Keeping that
boundary sharp is the reason this capability exists apart from evidence
fusion: "the vendor reports no incident" and "our infrastructure is at
fault" are different claims, and the component that gathers the first must
never be the one that asserts the second.
"""

from pathlib import Path
import json
import unittest

from vendor_health_agent import VendorHealthAgent


ROOT = Path(__file__).resolve().parent
JSON_DIR = ROOT / "json"
POLICY = ROOT / "config" / "vendor_health_policy.json"

GITHUB_ENTITIES = {"AS-GITHUB-ENTERPRISE", "COMP-GITHUB-REPO-ACCESS"}
TEAMS_ENTITIES = {"AS-TEAMS", "COMP-TEAMS-SIGNALING"}
ALL_ENTITIES = GITHUB_ENTITIES | TEAMS_ENTITIES

# Inside the freshness window for the current advisories.
ASSESSED_AT = "2026-07-16 09:15:00"


def agent() -> VendorHealthAgent:
    return VendorHealthAgent(JSON_DIR, POLICY)


def assess(entity_ids=None, as_of: str = ASSESSED_AT):
    return agent().assess(
        scenario_id="SCN-CROSS-GATEWAY-001",
        entity_ids=set(entity_ids if entity_ids is not None else ALL_ENTITIES),
        as_of=as_of,
    )


def finding(result, advisory_id: str):
    return next(f for f in result.findings if f.advisory_id == advisory_id)


class VendorIndependenceTests(unittest.TestCase):
    def test_each_vendor_is_represented_separately(self):
        result = assess()
        self.assertEqual(
            sorted(result.vendors_reporting_healthy),
            ["GitHub", "Microsoft"],
        )
        self.assertEqual(
            sorted(result.eliminated_external_hypotheses),
            ["EXTERNAL_GITHUB_OUTAGE", "EXTERNAL_MICROSOFT_OUTAGE"],
        )

    def test_a_github_record_never_speaks_for_microsoft(self):
        result = assess(GITHUB_ENTITIES)
        self.assertEqual(result.vendors_reporting_healthy, ["GitHub"])
        self.assertEqual(
            result.eliminated_external_hypotheses,
            ["EXTERNAL_GITHUB_OUTAGE"],
        )

    def test_a_microsoft_record_never_speaks_for_github(self):
        result = assess(TEAMS_ENTITIES)
        self.assertEqual(result.vendors_reporting_healthy, ["Microsoft"])
        self.assertEqual(
            result.eliminated_external_hypotheses,
            ["EXTERNAL_MICROSOFT_OUTAGE"],
        )

    def test_unrelated_entities_return_no_vendor_evidence(self):
        result = assess({"COMP-PAY-CONNECTOR"})
        self.assertEqual(result.findings, [])
        self.assertEqual(result.eliminated_external_hypotheses, [])


class EvidenceQualityTests(unittest.TestCase):
    def test_fresh_authoritative_evidence_eliminates_its_own_hypothesis(self):
        item = finding(assess(), "VND-GITHUB-001")
        self.assertTrue(item.is_fresh)
        self.assertTrue(item.is_trusted)
        self.assertTrue(item.eliminates_external_hypothesis)
        self.assertEqual(item.disqualification_reasons, [])

    def test_stale_evidence_cannot_eliminate_anything(self):
        item = finding(assess(), "VND-GITHUB-STALE-001")
        self.assertFalse(item.is_fresh)
        self.assertFalse(item.eliminates_external_hypothesis)
        self.assertIn("STALE_BEYOND_FRESHNESS_WINDOW", item.disqualification_reasons)

    def test_untrusted_source_cannot_eliminate_anything(self):
        item = finding(assess(), "VND-COMMUNITY-001")
        self.assertFalse(item.is_trusted)
        self.assertFalse(item.eliminates_external_hypothesis)
        self.assertIn(
            "SOURCE_AUTHORITY_NOT_TRUSTED",
            item.disqualification_reasons,
        )

    def test_a_trusted_record_goes_stale_as_the_window_passes(self):
        """The same record stops qualifying purely with age."""
        fresh = finding(assess(as_of="2026-07-16 09:15:00"), "VND-GITHUB-001")
        self.assertTrue(fresh.eliminates_external_hypothesis)

        later = finding(assess(as_of="2026-07-16 23:00:00"), "VND-GITHUB-001")
        self.assertFalse(later.eliminates_external_hypothesis)
        self.assertIn("STALE_BEYOND_FRESHNESS_WINDOW", later.disqualification_reasons)

    def test_evidence_published_after_the_assessment_is_rejected(self):
        item = finding(assess(as_of="2026-07-16 08:00:00"), "VND-GITHUB-001")
        self.assertFalse(item.is_fresh)
        self.assertIn("PUBLISHED_AFTER_ASSESSMENT", item.disqualification_reasons)

    def test_stale_evidence_is_retained_rather_than_discarded(self):
        """Disqualified evidence stays visible with its provenance intact."""
        item = finding(assess(), "VND-GITHUB-STALE-001")
        self.assertEqual(item.source_authority, "VENDOR_OFFICIAL")
        self.assertTrue(item.source_reference)
        self.assertEqual(item.published_at, "2026-07-14 05:30:00")


class BoundaryOfVendorTruthTests(unittest.TestCase):
    def test_only_external_hypotheses_are_ever_eliminated(self):
        result = assess()
        for hypothesis in result.eliminated_external_hypotheses:
            self.assertTrue(
                hypothesis.startswith("EXTERNAL_"),
                f"{hypothesis} is not an external hypothesis",
            )

    def test_the_agent_never_names_an_internal_entity(self):
        """Healthy vendors say nothing about the gateway."""
        payload = json.dumps(VendorHealthAgent.to_dict(assess()))
        for internal in (
            "COMP-SECURE-WEB-GATEWAY",
            "COMP-GATEWAY-TLS-POLICY",
            "CHG-GATEWAY-001",
        ):
            self.assertNotIn(internal, payload)

    def test_the_agent_emits_no_confidence_movement(self):
        result = VendorHealthAgent.to_dict(assess())
        for forbidden in ("confidence_score", "confidence_credit", "hard_flags"):
            self.assertNotIn(forbidden, result)

    def test_every_record_declares_itself_synthetic(self):
        for item in assess().findings:
            with self.subTest(advisory=item.advisory_id):
                self.assertTrue(item.synthetic)

    def test_normalized_output_exposes_the_agreed_shape(self):
        item = finding(assess(), "VND-MSFT-001")
        for field in (
            "vendor", "service", "status", "incident_confirmed",
            "affected_scope", "observed_at", "published_at",
            "source_authority", "source_reference", "confidence", "synthetic",
        ):
            with self.subTest(field=field):
                self.assertTrue(hasattr(item, field))
        self.assertIsInstance(item.freshness_minutes, int)


class RegistrationTests(unittest.TestCase):
    def test_skill_and_agent_are_registered_together(self):
        catalog = json.loads(
            (ROOT / "config" / "skill_catalog.json").read_text(encoding="utf-8")
        )
        registry = json.loads(
            (ROOT / "config" / "agent_registry.json").read_text(encoding="utf-8")
        )
        skills = {s["skill_id"] for s in catalog["skills"]}
        self.assertIn("external_service_health", skills)

        vendor = next(
            a for a in registry["agents"] if a["agent_id"] == "vendor_health_agent"
        )
        self.assertEqual(vendor["skills"], ["external_service_health"])
        self.assertEqual(vendor["status"], "ACTIVE")
        self.assertIn("vendor_advisories", vendor["data_domains"])

    def test_exactly_one_agent_provides_the_new_skill(self):
        registry = json.loads(
            (ROOT / "config" / "agent_registry.json").read_text(encoding="utf-8")
        )
        providers = [
            a["agent_id"] for a in registry["agents"]
            if "external_service_health" in a.get("skills", [])
        ]
        self.assertEqual(providers, ["vendor_health_agent"])


if __name__ == "__main__":
    unittest.main()
