import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

from vde.errors import DuplicateEventError
from vde.models import CycleReport
from vde.store import InMemoryEventStore, SQLiteEventStore
from vde.testing import fake_evaluate


def make_report():
    return CycleReport(
        schema_version="0.1.0",
        station_id="ST-01",
        cycle_id="C-01",
        reported_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
    )


class TestEventStores(unittest.TestCase):
    def test_memory_store_get_and_duplicate(self):
        store = InMemoryEventStore()
        event = fake_evaluate(make_report(), datetime(2026, 10, 20, 15, 1, tzinfo=timezone.utc))
        store.insert(event)
        self.assertEqual(store.get(event.event_id), event)
        self.assertIsNone(store.get("missing"))
        with self.assertRaises(DuplicateEventError):
            store.insert(event)

    def test_sqlite_store_get_and_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            store = SQLiteEventStore(str(Path(folder) / "events.db"))
            event = fake_evaluate(make_report(), datetime(2026, 10, 20, 15, 1, tzinfo=timezone.utc))
            store.insert(event)
            self.assertEqual(store.get(event.event_id), event)
            self.assertIsNone(store.get("missing"))
            with self.assertRaises(DuplicateEventError):
                store.insert(event)

    def test_sqlite_data_survives_new_store(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "events.db")
            event = fake_evaluate(make_report(), datetime(2026, 10, 20, 15, 1, tzinfo=timezone.utc))
            SQLiteEventStore(path).insert(event)
            self.assertEqual(SQLiteEventStore(path).get(event.event_id), event)


if __name__ == "__main__":
    unittest.main()
