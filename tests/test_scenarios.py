"""Scenario runner.                                                   OWNER: Teammate B

Loads every scenarios/*.json, checks the file is well formed, then runs it
through rules.evaluate and compares with `expected`. Until the rules engine is
finished, the evaluation tests are SKIPPED (not failed), so the suite stays green.
"""
import json
import pathlib
import unittest
from datetime import datetime, timezone

from vde.enums import EventState, ReasonCode
from vde.models import CycleReport
from vde.rules import evaluate

SCENARIO_DIR = pathlib.Path(__file__).resolve().parents[1] / "scenarios"
NOW = datetime(2026, 10, 20, 15, 1, tzinfo=timezone.utc)


def load_scenarios():
    return [(p.stem, json.loads(p.read_text())) for p in sorted(SCENARIO_DIR.glob("*.json"))]


class TestScenarioFiles(unittest.TestCase):
    """Runs today: every scenario file must be valid."""

    def test_at_least_one_scenario(self):
        self.assertTrue(load_scenarios(), "no scenarios found")

    def test_files_are_well_formed(self):
        for name, sc in load_scenarios():
            with self.subTest(scenario=name):
                self.assertEqual(sc["name"], name, "name must match file name")
                self.assertIn("description", sc)
                CycleReport.model_validate(sc["report"])
                EventState(sc["expected"]["state"])
                for r in sc["expected"]["reasons"]:
                    ReasonCode(r)


class TestScenarioOutcomes(unittest.TestCase):
    """Runs once vde.rules.evaluate is implemented."""

    def test_expected_outcomes(self):
        for name, sc in load_scenarios():
            with self.subTest(scenario=name):
                report = CycleReport.model_validate(sc["report"])
                try:
                    event = evaluate(report, NOW)
                except NotImplementedError:
                    self.skipTest("rules engine not implemented yet")
                exp = sc["expected"]
                self.assertEqual(event.state.value, exp["state"])
                self.assertEqual([r.value for r in event.reasons], exp["reasons"])
                if "deposit_volume_ml" in exp:
                    self.assertEqual(event.deposit_volume_ml, exp["deposit_volume_ml"])

    def test_evaluate_is_deterministic(self):
        for name, sc in load_scenarios():
            with self.subTest(scenario=name):
                report = CycleReport.model_validate(sc["report"])
                try:
                    a, b = evaluate(report, NOW), evaluate(report, NOW)
                except NotImplementedError:
                    self.skipTest("rules engine not implemented yet")
                self.assertEqual(a.model_dump(), b.model_dump())


if __name__ == "__main__":
    unittest.main()
