import json
import pathlib
import unittest
from datetime import datetime, timezone

from vde.errors import EventConflictError
from vde.models import CycleReport
from vde.service import submit_report
from vde.store import InMemoryEventStore
from vde.testing import fake_evaluate

NOW = datetime(2026, 10, 20, 15, 1, tzinfo=timezone.utc)
HAPPY = json.loads((pathlib.Path(__file__).resolve().parents[1] / "scenarios" / "happy_path.json").read_text())


def happy_report(**changes):
    data = {**HAPPY["report"], **changes}
    return CycleReport.model_validate(data)


class TestSubmitReport(unittest.TestCase):
    def test_first_submission_creates_event(self):
        store = InMemoryEventStore()
        event, created = submit_report(happy_report(), store, NOW, fake_evaluate)
        self.assertTrue(created)
        self.assertEqual(store.get(event.event_id), event)

    def test_same_report_returns_existing_event(self):
        store = InMemoryEventStore()
        first, created = submit_report(happy_report(), store, NOW, fake_evaluate)
        second, created_again = submit_report(happy_report(), store, NOW, fake_evaluate)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first, second)

    def test_changed_report_same_cycle_conflicts(self):
        store = InMemoryEventStore()
        submit_report(happy_report(), store, NOW, fake_evaluate)
        changed = happy_report(volume={**HAPPY["report"]["volume"], "validated_ml": 999.0})
        with self.assertRaises(EventConflictError):
            submit_report(changed, store, NOW, fake_evaluate)


if __name__ == "__main__":
    unittest.main()
