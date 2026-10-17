"""Step 1 tests: state machine, identifiers and schema invariants.

Run with either:   python -m pytest      or      python -m unittest discover -s tests
"""
import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from vde.enums import EventState as S, ReasonCode, TERMINAL_STATES
from vde.identity import derive_event_id
from vde.models import CycleReport, DisposalEvent, RuleResult
from vde.state import InvalidTransitionError, can_transition, is_terminal, transition

NOW = datetime(2026, 10, 7, 19, 46, tzinfo=timezone.utc)


def make_event(**overrides):
    base = dict(
        event_id="e1", state=S.VERIFIED, station_id="ST-01", cycle_id="C-1",
        receptacle_id="R-9", account_id="ACC-1", deposit_volume_ml=250.0,
        sanitation_fluid_ml=30.0, created_at=NOW, source_payload_hash="abc",
        rule_results=[RuleResult(rule_id="R1_IDENTITY", passed=True)],
    )
    base.update(overrides)
    return DisposalEvent(**base)


class TestStateMachine(unittest.TestCase):
    def test_happy_path(self):
        s = S.ATTEMPTED
        for nxt in (S.IN_PROGRESS, S.COMPLETED, S.VERIFIED):
            s = transition(s, nxt)
        self.assertEqual(s, S.VERIFIED)

    def test_attempted_cannot_jump_to_verified(self):
        # "Attempted, completed and verified events are not equivalent."
        self.assertFalse(can_transition(S.ATTEMPTED, S.VERIFIED))
        self.assertFalse(can_transition(S.IN_PROGRESS, S.VERIFIED))

    def test_rejection_only_before_completion(self):
        self.assertTrue(can_transition(S.ATTEMPTED, S.REJECTED))
        self.assertTrue(can_transition(S.IN_PROGRESS, S.REJECTED))
        self.assertFalse(can_transition(S.COMPLETED, S.REJECTED))

    def test_terminal_states_are_immutable(self):
        for terminal in TERMINAL_STATES:
            self.assertTrue(is_terminal(terminal))
            for target in S:
                with self.assertRaises(InvalidTransitionError):
                    transition(terminal, target)


class TestEventId(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(derive_event_id("ST-01", "C-1"), derive_event_id("ST-01", "C-1"))

    def test_distinct_per_station_and_cycle(self):
        ids = {derive_event_id("ST-01", "C-1"), derive_event_id("ST-02", "C-1"),
               derive_event_id("ST-01", "C-2")}
        self.assertEqual(len(ids), 3)

    def test_requires_both_parts(self):
        with self.assertRaises(ValueError):
            derive_event_id("", "C-1")


class TestCycleReportSchema(unittest.TestCase):
    def test_minimal_report_is_accepted(self):
        r = CycleReport(schema_version="0.1.0", station_id="ST-01", cycle_id="C-1",
                        reported_at=NOW)
        self.assertIsNone(r.account_id)  # missing account -> handled by rules, not schema

    def test_missing_station_id_is_refused(self):
        with self.assertRaises(ValidationError):
            CycleReport(schema_version="0.1.0", cycle_id="C-1", reported_at=NOW)

    def test_naive_timestamp_is_refused(self):
        with self.assertRaises(ValidationError):
            CycleReport(schema_version="0.1.0", station_id="ST-01", cycle_id="C-1",
                        reported_at=datetime(2026, 10, 7, 19, 46))

    def test_unknown_field_is_refused(self):
        with self.assertRaises(ValidationError):
            CycleReport(schema_version="0.1.0", station_id="ST-01", cycle_id="C-1",
                        reported_at=NOW, stationId="oops")

    def test_negative_volume_is_refused(self):
        with self.assertRaises(ValidationError):
            CycleReport(schema_version="0.1.0", station_id="ST-01", cycle_id="C-1",
                        reported_at=NOW, volume={"validated_ml": -5})


class TestDisposalEventInvariants(unittest.TestCase):
    def test_valid_verified_event(self):
        e = make_event()
        self.assertEqual(e.model_dump(mode="json")["created_at"], "2026-10-07T19:46:00.000Z")

    def test_verified_requires_account(self):
        with self.assertRaises(ValidationError):
            make_event(account_id=None)

    def test_verified_requires_volume(self):
        with self.assertRaises(ValidationError):
            make_event(deposit_volume_ml=None)

    def test_verified_cannot_have_reasons(self):
        with self.assertRaises(ValidationError):
            make_event(reasons=[ReasonCode.VOLUME_MISMATCH])

    def test_verified_cannot_have_failed_rule(self):
        with self.assertRaises(ValidationError):
            make_event(rule_results=[RuleResult(rule_id="R3_VOLUME", passed=False)])

    def test_rejected_requires_reason(self):
        with self.assertRaises(ValidationError):
            make_event(state=S.REJECTED, account_id=None, deposit_volume_ml=None)
        e = make_event(state=S.REJECTED, account_id=None, deposit_volume_ml=None,
                       reasons=[ReasonCode.ACCOUNT_MISSING])
        self.assertEqual(e.state, S.REJECTED)


if __name__ == "__main__":
    unittest.main()
