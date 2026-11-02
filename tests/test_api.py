import json
import pathlib
import unittest
from fastapi.testclient import TestClient

from vde import api
from vde.store import InMemoryEventStore

HAPPY = json.loads((pathlib.Path(__file__).resolve().parents[1] / "scenarios" / "happy_path.json").read_text())


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.old_store = api.store
        api.store = InMemoryEventStore()
        self.client = TestClient(api.app)

    def tearDown(self):
        api.store = self.old_store

    def test_health(self):
        response = self.client.get("/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_create_then_repeat(self):
        first = self.client.post("/v1/events", json=HAPPY["report"])
        second = self.client.post("/v1/events", json=HAPPY["report"])
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["event_id"], second.json()["event_id"])

    def test_conflicting_report(self):
        self.client.post("/v1/events", json=HAPPY["report"])
        changed = dict(HAPPY["report"])
        changed["volume"] = {**HAPPY["report"]["volume"], "validated_ml": 999.0}
        response = self.client.post("/v1/events", json=changed)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "EVENT_CONFLICT")

    def test_invalid_report(self):
        response = self.client.post("/v1/events", json={"station_id": "ST-01"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")

    def test_get_event_and_missing_event(self):
        created = self.client.post("/v1/events", json=HAPPY["report"])
        event_id = created.json()["event_id"]
        found = self.client.get(f"/v1/events/{event_id}")
        missing = self.client.get("/v1/events/not-found")
        self.assertEqual(found.status_code, 200)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"]["code"], "EVENT_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
