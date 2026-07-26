"""Where a belief came from, and what that is worth.

Until now every recorded case counted the same. A success the system observed
unsupervised, a plan a human had to correct, and a finding another agent
contributed were all one row of history with one weight. That treats the
approval field as decoration, which is what it had become: 108 records, 108
approvals, and 22 recorded human corrections nothing ever read.

Two rules are asserted here. Authority attenuates through delegation — an
agent's standing over what it is asserting bounds what its assertion is worth,
independently of how reliable that agent is elsewhere. Trust attenuates through
transfer — second-hand belief is real evidence and can never outweigh the
firsthand kind.
"""

from datetime import datetime
from pathlib import Path
import unittest

from adaptive_execution_orchestrator import AdaptiveExecutionOrchestrator
from operational_confidence_engine import OperationalConfidenceEngine


ROOT = Path(__file__).resolve().parent


def engine() -> OperationalConfidenceEngine:
    return OperationalConfidenceEngine(
        ROOT / "json", ROOT / "config" / "confidence_policy.json"
    )


def profile(known_error_id: str):
    return engine()._outcome_profile(
        known_error_id=known_error_id, assessed_at=datetime(2026, 6, 1)
    )


class ProvenanceIsDerivedTests(unittest.TestCase):
    """No fixture declares a provenance class. Each is read off the record."""

    def test_an_amended_recommendation_counts_as_human_verified(self):
        row = {"human_modification": "Added downstream health validation"}
        self.assertEqual(engine()._provenance_of(row), "HUMAN_VERIFIED")

    def test_a_declined_recommendation_counts_as_human_verified(self):
        row = {"approval_decision": "Rejected", "human_modification": "None"}
        self.assertEqual(engine()._provenance_of(row), "HUMAN_VERIFIED")

    def test_an_unamended_approval_is_only_a_self_outcome(self):
        """A rubber stamp is not verification, whatever the field says."""
        row = {"approval_decision": "Approved", "human_modification": "None"}
        self.assertEqual(engine()._provenance_of(row), "SELF_OUTCOME")

    def test_an_agent_established_record_counts_as_peer(self):
        row = {
            "approval_decision": "Approved",
            "established_by_agent": "vendor_health_agent",
        }
        self.assertEqual(engine()._provenance_of(row), "PEER_AGENT")

    def test_the_fixtures_never_declare_the_class(self):
        payload = (ROOT / "json" / "outcome_history.json").read_text(
            encoding="utf-8"
        )
        for name in ("SELF_OUTCOME", "HUMAN_VERIFIED", "PEER_AGENT"):
            with self.subTest(name=name):
                self.assertNotIn(name, payload)


class TrustWeightingTests(unittest.TestCase):
    def test_human_correction_outranks_bare_approval(self):
        e = engine()
        corrected = e._provenance_weight(
            {"human_modification": "Restricted rollback to affected categories"}
        )
        stamped = e._provenance_weight(
            {"approval_decision": "Approved", "human_modification": "None"}
        )
        self.assertGreater(corrected, stamped)

    def test_a_peer_finding_within_its_remit_still_counts(self):
        weight = engine()._provenance_weight(
            {
                "established_by_agent": "vendor_health_agent",
                "established_for_domain": "vendor_advisories",
            }
        )
        self.assertGreater(weight, 0.5)

    def test_standing_not_reliability_decides_what_a_peer_is_worth(self):
        """The telemetry agent is the more reliable of the two and counts for
        far less here, because vendor advisories are not its to assert."""
        e = engine()
        registry = e.agent_registry
        self.assertGreater(
            registry["telemetry_analysis_agent"]["reliability_score"],
            registry["vendor_health_agent"]["reliability_score"],
        )
        in_standing = e._provenance_weight(
            {
                "established_by_agent": "vendor_health_agent",
                "established_for_domain": "vendor_advisories",
            }
        )
        out_of_standing = e._provenance_weight(
            {
                "established_by_agent": "telemetry_analysis_agent",
                "established_for_domain": "vendor_advisories",
            }
        )
        self.assertLess(out_of_standing, in_standing)
        self.assertLess(out_of_standing, 0.15)

    def test_transfer_never_amplifies(self):
        """No peer, however reliable, outweighs the system's own experience."""
        e = engine()
        firsthand = e._provenance_weight(
            {"approval_decision": "Approved", "human_modification": "None"}
        )
        for agent_id, agent in e.agent_registry.items():
            with self.subTest(agent=agent_id):
                weight = e._provenance_weight(
                    {
                        "established_by_agent": agent_id,
                        "established_for_domain": next(
                            iter(agent.get("data_domains", ["none"])), "none"
                        ),
                    }
                )
                self.assertLessEqual(weight, firsthand)
                self.assertLessEqual(
                    weight,
                    e.trust_policy["attenuation"]["maximum_peer_trust"],
                )


class SupervisionTests(unittest.TestCase):
    def test_amendment_history_is_now_visible(self):
        """22 recorded corrections that no code path read."""
        self.assertGreater(profile("KE-QUEUE-002").modification_rate, 0.0)

    def test_the_penalty_is_graded_rather_than_stepped(self):
        """A case at the threshold and a case just past it should not differ
        by the whole penalty; nothing in the evidence supports a cliff."""
        e = engine()
        policy = e.trust_policy["supervision"]
        gateway = profile("KE-GATEWAY-001")
        queue = profile("KE-QUEUE-002")
        self.assertAlmostEqual(
            gateway.modification_rate,
            float(policy["modification_rate_threshold"]),
            places=3,
        )
        self.assertGreater(queue.modification_rate, gateway.modification_rate)

        def penalty(scenario: str) -> float:
            return (
                e.assess(scenario)
                .penalty_scores.get("frequently_amended_by_humans", 0.0)
            )

        self.assertEqual(penalty("SCN-CROSS-GATEWAY-001"), 0.0)
        queue_penalty = penalty("SCN-QUEUE-001")
        self.assertGreater(queue_penalty, 0.0)
        self.assertLess(
            queue_penalty, float(policy["modification_rate_penalty"])
        )

    def test_the_flag_raises_later_than_the_penalty(self):
        """Amendment should cost confidence before it costs plan eligibility."""
        policy = engine().trust_policy["supervision"]
        self.assertGreater(
            float(policy["modification_rate_flag_threshold"]),
            float(policy["modification_rate_threshold"]),
        )

    def test_a_rate_over_one_record_is_not_a_rate(self):
        """One amended case out of one reads as 100% and must not be charged
        as though it were an established pattern of amendment."""
        e = engine()
        policy = e.trust_policy["supervision"]
        floor = int(policy["minimum_sample_for_supervision_signal"])
        self.assertGreater(floor, 1)
        for known_error_id in ("KE-PAY-001", "KE-QUEUE-002"):
            with self.subTest(known_error_id=known_error_id):
                self.assertGreaterEqual(
                    profile(known_error_id).sample_size, floor
                )

    def test_a_declined_recommendation_is_not_recorded_as_a_success(self):
        rows = [
            row
            for row in engine().outcomes
            if str(row.get("approval_decision", "")).lower() == "rejected"
        ]
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(outcome_id=row["outcome_id"]):
                self.assertNotEqual(row["outcome"], "Successful")


class PeerHeldExperienceTests(unittest.TestCase):
    def test_a_pattern_known_only_at_second_hand_is_named_as_such(self):
        mix = profile("KE-VENDOR-SAAS-001").provenance_mix
        self.assertEqual(mix["PEER_AGENT"], 10)
        self.assertEqual(mix["SELF_OUTCOME"], 0)
        self.assertEqual(mix["HUMAN_VERIFIED"], 0)

    def test_second_hand_success_does_not_read_as_firsthand_reliability(self):
        """A high success rate held entirely by peers is discounted, because
        the system has never carried this out itself."""
        peer_held = profile("KE-VENDOR-SAAS-001")
        firsthand = profile("KE-PAY-001")
        self.assertGreater(peer_held.weighted_success_rate, 0.8)
        self.assertLess(peer_held.reliability_score, firsthand.reliability_score)


class StandingFlagTests(unittest.TestCase):
    """Flags about the evidence base behave differently from flags about the
    run. Both cost confidence; only one can ever be answered."""

    def test_a_standing_flag_does_not_hold_the_credit_gate_shut_forever(self):
        limits = engine()._read(
            ROOT / "config" / "runtime_signal_policy.json"
        )["limits"]
        exempt = set(limits["standing_flags_exempt_from_credit_gate"])
        self.assertIn("RECOMMENDATION_FREQUENTLY_AMENDED", exempt)
        self.assertTrue(limits["credits_require_no_unresolved_hard_flags"])

    def test_it_still_bars_the_accelerated_plan(self):
        """Exempting a flag from the credit gate must not quietly exempt it
        from plan eligibility, which is where it does its actual work."""
        policies = engine()._read(ROOT / "config" / "orchestration_policies.json")
        accelerated = next(
            mode
            for mode in policies["modes"]
            if mode["mode_id"] == "ACCELERATED_VALIDATION"
        )
        self.assertIn(
            "EXPERIENCE_TRANSFERRED_NOT_DIRECT",
            accelerated["entry_conditions"]["disallowed_hard_flags"],
        )

    def test_the_amended_pattern_never_reaches_the_narrow_plan(self):
        result = AdaptiveExecutionOrchestrator(ROOT).execute(
            correlation_id="TEST-PROVENANCE-QUEUE",
            scenario_id="SCN-QUEUE-001",
        )
        self.assertEqual(result.final_plan_mode, "FULL_INVESTIGATION")
        self.assertTrue(result.recommendation["human_approval_required"])


if __name__ == "__main__":
    unittest.main()
