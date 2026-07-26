"""Structural guards against the fault that produced this correction.

Five faults of one shape were found across two sprints: a judgement derived
independently in two places, or a fact read by one layer and not the other.
Each was internally correct where it sat, so no behavioural test caught any of
them. They were caught by a person noticing, which is not a control.

These checks are static — they parse and read the sources, and need no
runtime. They do not assert that the architecture is good. They assert that a
specific, repeatedly-made mistake cannot be made again silently.

Every exception is declared here with a reason. An exception nobody can state
a reason for is the thing this file exists to prevent, and an allowlist that
grows without justification is how a guard becomes decoration.
"""

from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"

# The two layers that must never disagree.
ENGINE = "operational_confidence_engine.py"
FUSION = "evidence_fusion_agent.py"
LEDGER = "experience_ledger.py"


# Tooling that observes the system rather than participating in a run. These
# read policy in order to report it — the deck quotes the ceilings and weights
# on its slides, the rehearsal prints what the demo will show — and neither
# takes part in an assessment. Anything here that started making decisions
# would be a defect this guard could no longer see, so the list is explicit and
# short rather than a filename pattern that could quietly swallow a module.
OBSERVERS = frozenset({"build_deck.py", "rehearse.py"})


def modules() -> list[Path]:
    """Modules that participate in a run.

    Tests, demos and the observers above may read anything they like; they
    cannot cause two layers to disagree because they are not layers.
    """
    return sorted(
        path
        for path in ROOT.glob("*.py")
        if not path.name.startswith(("test_", "demo_"))
        and path.name not in OBSERVERS
    )


def readers_of(needle: str) -> set[str]:
    return {
        path.name
        for path in modules()
        if needle in path.read_text(encoding="utf-8")
    }


class SharedFactsHaveOneReaderTests(unittest.TestCase):
    """A fixture read by one layer and not the other is a divergent past.

    Fusion did not read runtime outcome feedback for the whole of its
    existence, so everything the system learned at runtime was visible to the
    planner and invisible to the explainer.
    """

    # Facts about experience. Both layers need them, so neither loads them:
    # the ledger does, on behalf of both.
    LEDGER_OWNED = (
        "outcome_history.json",
        "runtime_outcome_feedback.json",
        "known_errors.json",
        "learned_patterns.json",
        "refutation_ledger.json",
    )

    def test_experience_fixtures_are_loaded_by_the_ledger(self):
        for fixture in self.LEDGER_OWNED:
            with self.subTest(fixture=fixture):
                self.assertIn(
                    fixture,
                    (ROOT / LEDGER).read_text(encoding="utf-8"),
                    f"{fixture} is a fact about experience and the ledger "
                    f"should own loading it",
                )

    def test_neither_layer_loads_experience_behind_the_ledger(self):
        """Loading it directly is how the two copies drift apart."""
        for layer in (ENGINE, FUSION):
            source = (ROOT / layer).read_text(encoding="utf-8")
            for fixture in self.LEDGER_OWNED:
                with self.subTest(layer=layer, fixture=fixture):
                    self.assertNotIn(
                        f'"{fixture}"',
                        source,
                        f"{layer} loads {fixture} itself instead of reading "
                        f"through the ledger",
                    )


class PolicyHasOneInterpreterTests(unittest.TestCase):
    """Two interpreters of one policy is the shape of every fault found.

    Reading a policy to *display* it is not interpreting it. Reading it to
    *decide* something is, and that must happen in one place.
    """

    # Declared exceptions, each with the reason it is not a divergence risk.
    DECLARED = {
        "agent_registry.json": (
            "Identity and standing lookups, not policy interpretation. The "
            "orchestrator enforces registration, the engine and fusion read "
            "an agent's standing over a claim; none decides what the registry "
            "means."
        ),
        "automation_readiness_policy.json": (
            "eaios_story_data reads one threshold to draw a line on a chart. "
            "It displays what the policy says rather than deciding anything, "
            "so it cannot disagree with the run it is showing."
        ),
        "runtime_signal_policy.json": (
            "eaios_story_data reads the penalty and credit figures to show "
            "that recovery is capped below loss. Display only."
        ),
        "experience_trust_policy.json": (
            "Same: both layers pass it to the ledger, which applies it once."
        ),
        "vendor_health_policy.json": (
            "The vendor agent applies it; the orchestrator names the file to "
            "construct that agent."
        ),
        "orchestration_policies.json": (
            "threshold_explorer reads the accelerated mode's disallowed flags "
            "so the controls panel can name what is holding a scenario in the "
            "full plan. It reads them in order to report them and never "
            "decides entry itself; reading rather than restating is what stops "
            "the panel drifting from what actually blocks a plan."
        ),
        "confidence_policy.json": (
            "Fusion reads it solely to construct the shared ledger with the "
            "same weighting the engine uses, and threshold_explorer reads the "
            "shipped bands to seed the sliders and rewrite them in a temporary "
            "copy. Neither interprets it independently."
        ),
        "servicenow_field_mapping.json": (
            "Field discovery writes the mapping and sync consumes it. A "
            "producer and a consumer of one artefact, not two interpreters."
        ),
    }

    def test_every_multi_reader_policy_is_declared(self):
        for policy in sorted(CONFIG.glob("*.json")):
            readers = readers_of(policy.name)
            if len(readers) <= 1:
                continue
            with self.subTest(policy=policy.name):
                self.assertIn(
                    policy.name,
                    self.DECLARED,
                    f"{policy.name} is read by {sorted(readers)}. If that is "
                    f"deliberate, declare it here with the reason; if it is "
                    f"not, the second reader is deciding something the first "
                    f"already decided.",
                )

    def test_an_observer_never_becomes_a_participant(self):
        """The exclusion is only safe while these modules stay read-only.
        If one starts orchestrating, the guard stops seeing it."""
        from test_architecture_invariants import OBSERVERS

        for name in OBSERVERS:
            source = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(module=name):
                self.assertNotIn(
                    "def execute(", source,
                    f"{name} is excluded from the guard as an observer and "
                    f"now looks like a participant",
                )

    def test_no_declaration_outlives_its_reason(self):
        """An allowlist that keeps stale entries stops meaning anything."""
        for policy in self.DECLARED:
            with self.subTest(policy=policy):
                self.assertGreater(
                    len(readers_of(policy)),
                    1,
                    f"{policy} no longer has multiple readers; remove the "
                    f"declaration rather than leaving it to cover a future "
                    f"one nobody examined",
                )


class JudgementsAreMadeOnceTests(unittest.TestCase):
    """The specific judgements that have already been made twice."""

    # marker -> how many production modules may legitimately mention it
    SINGLE_SITE = {
        # The eligibility rule for knowledge. Fusion asks the reasoner.
        "minimum_symptom_coverage": 1,
        # When documentation is reconsulted. The engine decides, fusion is told.
        "reconsult_below_confidence": 1,
        # What a document may be worth. Scaled in one place.
        "maximum_documented_confidence": 1,
        # Which patterns are recallable.
        "admissible_knowledge_statuses": 1,
        # How a case is weighted.
        "provenance_weights": 1,
    }

    def test_each_judgement_has_one_site(self):
        for marker, allowed in self.SINGLE_SITE.items():
            holders = readers_of(marker)
            with self.subTest(judgement=marker):
                self.assertLessEqual(
                    len(holders),
                    allowed,
                    f"{marker} is interpreted in {sorted(holders)}; a rule "
                    f"read in several places is a rule decided in several "
                    f"places",
                )

    def test_sufficiency_is_defined_once(self):
        """Promotion once carried its own number and disagreed with the flag
        that gates the same question."""
        holders = readers_of("minimum_outcome_sample")
        self.assertLessEqual(len(holders), 2, sorted(holders))

    def test_fusion_receives_the_reconsultation_decision(self):
        tree = ast.parse((ROOT / FUSION).read_text(encoding="utf-8"))
        analyze = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "analyze"
        )
        self.assertIn(
            "reconsult_documentation",
            {arg.arg for arg in analyze.args.kwonlyargs},
            "fusion decides for itself again whether recall was thin",
        )


class FlagsArePlacedDeliberatelyTests(unittest.TestCase):
    """Three tiers, and every flag belongs to one on purpose.

    A flag that blocks a plan by accident is how plan control leaks away from
    operational confidence.
    """

    def _policy(self, name: str) -> dict:
        import json

        return json.loads((CONFIG / name).read_text(encoding="utf-8"))

    def test_informational_flags_have_no_plan_effect(self):
        """These reopen the knowledge search and disclose what it found.
        Neither is a reason to refuse a plan."""
        informational = {
            "WEAK_PATTERN_DOCUMENTATION_RECONSULTED",
            "NEWER_DOCUMENTATION_AVAILABLE",
        }
        accelerated = next(
            mode
            for mode in self._policy("orchestration_policies.json")["modes"]
            if mode["mode_id"] == "ACCELERATED_VALIDATION"
        )
        blocking = set(accelerated["entry_conditions"]["disallowed_hard_flags"])
        suspending = set(
            self._policy("automation_readiness_policy.json")[
                "suspension_hard_flags"
            ]
        )
        self.assertEqual(informational & blocking, set())
        self.assertEqual(informational & suspending, set())

    def test_nothing_unbacked_by_own_experience_can_be_automated(self):
        suspending = set(
            self._policy("automation_readiness_policy.json")[
                "suspension_hard_flags"
            ]
        )
        for flag in (
            "HYPOTHESIS_FROM_DOCUMENTATION_ONLY",
            "EXPERIENCE_TRANSFERRED_NOT_DIRECT",
            "EXPERIENCE_HELD_ONLY_BY_PEER_AGENT",
            "PATTERN_PROVISIONAL_NOT_ESTABLISHED",
            "REMEDY_PREVIOUSLY_INEFFECTIVE",
            "PATTERN_ACCOUNT_PREVIOUSLY_REJECTED",
        ):
            with self.subTest(flag=flag):
                self.assertIn(flag, suspending)

    def test_standing_flags_do_not_hold_the_credit_gate_shut(self):
        """No runtime signal can resolve them, so gating credit on them would
        withhold it permanently rather than pending an answer."""
        exempt = set(
            self._policy("runtime_signal_policy.json")["limits"][
                "standing_flags_exempt_from_credit_gate"
            ]
        )
        for flag in (
            "PATTERN_PROVISIONAL_NOT_ESTABLISHED",
            "PATTERN_ACCOUNT_PREVIOUSLY_REJECTED",
            "RECOMMENDATION_FREQUENTLY_AMENDED",
        ):
            with self.subTest(flag=flag):
                self.assertIn(flag, exempt)


if __name__ == "__main__":
    unittest.main()
