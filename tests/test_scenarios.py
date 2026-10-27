"""Scenario runner.                                                   OWNER: Teammate B

Loads every scenarios/*.json and tests it in two layers:

  1. TestScenarioFiles / TestScenarioCoverage -- run TODAY. Each file must be
     well formed, its `expected` block must agree with the state model
     (precedence, rule order, no deposit on REJECTED), and together the files
     must cover every reason code and every terminal state.
  2. TestScenarioOutcomes -- runs once vde.rules.evaluate is implemented. Until
     then it is SKIPPED (not failed), so the suite stays green.

Team 5 can reuse the JSON files directly; see scenarios/README.md.
"""
import json
import pathlib
import unittest
from datetime import datetime, timezone

from vde.enums import TERMINAL_STATES, EventState, ReasonCode
from vde.identity import derive_event_id
from vde.models import CycleReport
from vde.rules import REASON_STATE, evaluate

SCENARIO_DIR = pathlib.Path(__file__).resolve().parents[1] / "scenarios"
NOW = datetime(2026, 10, 20, 15, 1, tzinfo=timezone.utc)

# Scenarios the project brief and STATE_MODEL.md section 6 require.
REQUIRED_SCENARIOS = {
    "happy_path", "identity_failure", "account_missing", "aborted_pre_extraction",
    "liquid_not_accepted", "volume_mismatch", "volume_low_confidence",
    "sanitation_incomplete", "post_extraction_fault", "missing_timestamp",
    "timestamps_out_of_order", "multiple_failures", "retry_then_success",
}

# Position of each reason's rule (R1..R9). `expected.reasons` must follow this order.
RULE_OF_REASON = {
    ReasonCode.IDENTITY_FAILURE: 1,
    ReasonCode.ACCOUNT_MISSING: 2,
    ReasonCode.LIQUID_NOT_ACCEPTED: 3,
    ReasonCode.ABORTED_PRE_EXTRACTION: 4,
    ReasonCode.POST_EXTRACTION_FAULT: 5,
    ReasonCode.STAGE_SEQUENCE_INVALID: 6,
    ReasonCode.MISSING_TIMESTAMP: 7,
    ReasonCode.TIMESTAMP_ORDER_INVALID: 7,
    ReasonCode.VOLUME_MISSING: 8,
    ReasonCode.VOLUME_MISMATCH: 8,
    ReasonCode.VOLUME_LOW_CONFIDENCE: 8,
    ReasonCode.SANITATION_INCOMPLETE: 9,
}

PRECEDENCE = (EventState.REJECTED, EventState.FAULTED, EventState.UNVERIFIED)
ALLOWED_TOP_KEYS = {"name", "description", "report", "expected"}
ALLOWED_EXPECTED_KEYS = {"state", "reasons", "deposit_volume_ml"}


def load_scenarios():
    return [(p.stem, json.loads(p.read_text())) for p in sorted(SCENARIO_DIR.glob("*.json"))]


def state_from_reasons(reasons):
    """What the state model says the state must be for this set of reasons."""
    forced = {REASON_STATE[r] for r in reasons}
    return next((s for s in PRECEDENCE if s in forced), EventState.VERIFIED)


def rules_engine_ready():
    """True once evaluate() is implemented (it raises NotImplementedError until then)."""
    _, happy = next(sc for sc in load_scenarios() if sc[0] == "happy_path")
    try:
        evaluate(CycleReport.model_validate(happy["report"]), NOW)
    except NotImplementedError:
        return False
    return True


class TestScenarioFiles(unittest.TestCase):
    """Runs today: every scenario file must be valid and self-consistent."""

    def test_at_least_one_scenario(self):
        self.assertTrue(load_scenarios(), "no scenarios found")

    def test_files_are_well_formed(self):
        for name, sc in load_scenarios():
            with self.subTest(scenario=name):
                self.assertEqual(set(sc), ALLOWED_TOP_KEYS, "unexpected or missing top-level keys")
                self.assertEqual(sc["name"], name, "name must match file name")
                self.assertTrue(sc["description"].strip(), "description must not be empty")
                CycleReport.model_validate(sc["report"])
                exp = sc["expected"]
                self.assertLessEqual(set(exp), ALLOWED_EXPECTED_KEYS, "unknown key in expected")
                self.assertIn(EventState(exp["state"]), TERMINAL_STATES, "expected state must be terminal")
                for r in exp["reasons"]:
                    ReasonCode(r)

    def test_expected_state_follows_precedence(self):
        # REJECTED > FAULTED > UNVERIFIED > VERIFIED (STATE_MODEL.md section 5)
        for name, sc in load_scenarios():
            with self.subTest(scenario=name):
                reasons = [ReasonCode(r) for r in sc["expected"]["reasons"]]
                self.assertEqual(state_from_reasons(reasons).value, sc["expected"]["state"])

    def test_expected_reasons_in_rule_order_without_duplicates(self):
        for name, sc in load_scenarios():
            with self.subTest(scenario=name):
                reasons = [ReasonCode(r) for r in sc["expected"]["reasons"]]
                self.assertEqual(len(reasons), len(set(reasons)), "duplicate reason")
                rule_numbers = [RULE_OF_REASON[r] for r in reasons]
                self.assertEqual(rule_numbers, sorted(rule_numbers), "reasons not in R1..R9 order")
                self.assertEqual(len(rule_numbers), len(set(rule_numbers)),
                                 "one rule produces at most one reason")

    def test_expected_deposit_volume_is_consistent(self):
        for name, sc in load_scenarios():
            with self.subTest(scenario=name):
                exp = sc["expected"]
                if "deposit_volume_ml" not in exp:
                    continue
                volume = sc["report"].get("volume") or {}
                validated = volume.get("validated_ml")
                if exp["state"] == "REJECTED" or validated is None:
                    # REJECTED = nothing deposited; no validated volume = nothing to report.
                    self.assertIsNone(exp["deposit_volume_ml"])
                else:
                    # User deposit only: validated_ml, never plus sanitation fluid.
                    self.assertEqual(exp["deposit_volume_ml"], validated)

    def test_cycle_ids_are_unique(self):
        # Distinct cycles -> distinct event ids, so all scenarios can share one store.
        seen = {}
        for name, sc in load_scenarios():
            key = (sc["report"]["station_id"], sc["report"]["cycle_id"])
            with self.subTest(scenario=name):
                self.assertNotIn(key, seen, f"same station/cycle as {seen.get(key)}")
            seen[key] = name


class TestScenarioCoverage(unittest.TestCase):
    """Runs today: the scenario set as a whole exercises the whole state model."""

    def test_required_scenarios_exist(self):
        names = {name for name, _ in load_scenarios()}
        self.assertFalse(REQUIRED_SCENARIOS - names, "missing required scenarios")

    def test_every_reason_code_is_exercised(self):
        used = {ReasonCode(r) for _, sc in load_scenarios() for r in sc["expected"]["reasons"]}
        self.assertEqual(set(ReasonCode) - used, set(), "reason codes with no scenario")

    def test_every_terminal_state_is_exercised(self):
        used = {EventState(sc["expected"]["state"]) for _, sc in load_scenarios()}
        self.assertEqual(set(TERMINAL_STATES) - used, set(), "terminal states with no scenario")


@unittest.skipUnless(rules_engine_ready(), "rules engine (vde.rules.evaluate) not implemented yet")
class TestScenarioOutcomes(unittest.TestCase):
    """Runs once vde.rules.evaluate is implemented."""

    def test_expected_outcomes(self):
        for name, sc in load_scenarios():
            with self.subTest(scenario=name):
                event = evaluate(CycleReport.model_validate(sc["report"]), NOW)
                exp = sc["expected"]
                self.assertEqual(event.state.value, exp["state"])
                self.assertEqual([r.value for r in event.reasons], exp["reasons"])
                if "deposit_volume_ml" in exp:
                    self.assertEqual(event.deposit_volume_ml, exp["deposit_volume_ml"])

    def test_event_contract_fields(self):
        # Fields from the evaluate() docstring that Teams 4/7 rely on.
        for name, sc in load_scenarios():
            with self.subTest(scenario=name):
                report = CycleReport.model_validate(sc["report"])
                event = evaluate(report, NOW)
                self.assertEqual(event.event_id, derive_event_id(report.station_id, report.cycle_id))
                self.assertEqual(event.station_id, report.station_id)
                self.assertEqual(event.cycle_id, report.cycle_id)
                self.assertEqual(event.receptacle_id, report.receptacle_id)
                self.assertEqual(event.account_id, report.account_id)
                self.assertEqual(event.retry_count, report.retry_count)
                self.assertEqual(event.faults, report.faults)
                self.assertEqual(event.created_at, NOW)
                self.assertEqual(len(event.rule_results), 9, "every rule must be recorded")
                failed = [rr.reason for rr in event.rule_results if not rr.passed]
                self.assertEqual(failed, event.reasons, "reasons must match failing rule_results")
                fluid = report.sanitation.fluid_ml if report.sanitation else None
                self.assertEqual(event.sanitation_fluid_ml, fluid, "sanitation fluid kept separate")

    def test_evaluate_is_deterministic(self):
        for name, sc in load_scenarios():
            with self.subTest(scenario=name):
                report = CycleReport.model_validate(sc["report"])
                a, b = evaluate(report, NOW), evaluate(report, NOW)
                self.assertEqual(a.model_dump(), b.model_dump())


if __name__ == "__main__":
    unittest.main()
