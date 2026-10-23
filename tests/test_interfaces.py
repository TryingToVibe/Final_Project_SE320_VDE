"""Tests for the shared pieces that are already complete (team lead).

Teammates: add your own test files (test_rules.py, test_store.py,
test_service.py, test_api.py). Do not delete these.
"""
import json
import pathlib
import unittest
from datetime import datetime, timezone

from vde.enums import EventState
from vde.errors import DuplicateEventError
from vde.identity import derive_event_id, payload_hash
from vde.models import CycleReport
from vde.rules import RULES, r1_identity
from vde.config import DEFAULT_CONFIG
from vde.store import InMemoryEventStore
from vde.testing import fake_evaluate

NOW = datetime(2026, 10, 20, 15, 1, tzinfo=timezone.utc)
HAPPY = json.loads((pathlib.Path(__file__).resolve().parents[1] / "scenarios" / "happy_path.json").read_text())


def happy_report(**changes):
    data = {**HAPPY["report"], **changes}
    return CycleReport.model_validate(data)


class TestPayloadHash(unittest.TestCase):
    def test_same_report_same_hash(self):
        self.assertEqual(payload_hash(happy_report()), payload_hash(happy_report()))

    def test_changed_report_different_hash(self):
        changed = happy_report(volume={**HAPPY["report"]["volume"], "validated_ml": 999.0})
        self.assertNotEqual(payload_hash(happy_report()), payload_hash(changed))

    def test_field_order_does_not_matter(self):
        reordered = dict(reversed(list(HAPPY["report"].items())))
        self.assertEqual(payload_hash(happy_report()), payload_hash(CycleReport.model_validate(reordered)))


class TestInMemoryStore(unittest.TestCase):
    def test_insert_get_and_duplicate(self):
        store = InMemoryEventStore()
        event = fake_evaluate(happy_report(), NOW)
        store.insert(event)
        self.assertEqual(store.get(event.event_id), event)
        self.assertIsNone(store.get("nope"))
        with self.assertRaises(DuplicateEventError):
            store.insert(event)


class TestFakeEvaluate(unittest.TestCase):
    def test_verified_and_rejected(self):
        self.assertEqual(fake_evaluate(happy_report(), NOW).state, EventState.VERIFIED)
        self.assertEqual(fake_evaluate(happy_report(account_id=None), NOW).state, EventState.REJECTED)
        self.assertEqual(fake_evaluate(happy_report(), NOW).event_id,
                         derive_event_id("ST-01", "C-HAPPY-001"))


class TestRuleExample(unittest.TestCase):
    """R1 is the worked example in rules.py."""

    def test_nine_rules_registered(self):
        self.assertEqual(len(RULES), 9)

    def test_r1(self):
        self.assertTrue(r1_identity(happy_report(), DEFAULT_CONFIG).passed)
        self.assertFalse(r1_identity(happy_report(receptacle_id=None), DEFAULT_CONFIG).passed)


if __name__ == "__main__":
    unittest.main()
