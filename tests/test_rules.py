"""Rules engine tests (R1-R9, decide_state, evaluate).          OWNER: Teammate A

Each test starts from scenarios/happy_path.json and changes one thing.
"""
import copy
import json
import pathlib
import unittest
from datetime import datetime, timezone

from vde.config import DEFAULT_CONFIG, VerificationConfig
from vde.enums import CycleStage, EventState as S, ReasonCode as R
from vde.identity import derive_event_id, payload_hash
from vde.models import CycleReport, RuleResult
from vde.rules import (
    RULES, decide_state, evaluate, r2_account, r3_liquid, r4_extraction,
    r5_no_post_extraction_fault, r6_completion, r7_timestamps, r8_volume, r9_sanitation,
)

NOW = datetime(2026, 10, 20, 15, 1, tzinfo=timezone.utc)
HAPPY = json.loads((pathlib.Path(__file__).resolve().parents[1] / "scenarios" / "happy_path.json").read_text())


def raw():
    """A fresh, mutable copy of the happy-path report dict."""
    return copy.deepcopy(HAPPY["report"])


def report(data=None, **changes):
    data = data if data is not None else raw()
    data.update(changes)
    return CycleReport.model_validate(data)


def stages_until(stage):
    """Happy-path stages up to and including `stage`."""
    out = []
    for s in raw()["stages"]:
        out.append(s)
        if s["stage"] == stage:
            return out
    raise ValueError(stage)


def with_volume(**vol):
    return report(volume={**raw()["volume"], **vol})


class TestRulesPassOnHappyPath(unittest.TestCase):
    def test_every_rule_passes(self):
        for rule in RULES:
            with self.subTest(rule=rule.__name__):
                self.assertTrue(rule(report(), DEFAULT_CONFIG).passed)


class TestR2Account(unittest.TestCase):
    def test_missing_account(self):
        res = r2_account(report(account_id=None), DEFAULT_CONFIG)
        self.assertFalse(res.passed)
        self.assertEqual(res.reason, R.ACCOUNT_MISSING)


class TestR3Liquid(unittest.TestCase):
    def test_liquid_stage_failed(self):
        data = raw()
        data["stages"][3]["passed"] = False  # LIQUID_ACCEPTED
        res = r3_liquid(report(data), DEFAULT_CONFIG)
        self.assertEqual(res.reason, R.LIQUID_NOT_ACCEPTED)

    def test_liquid_stage_not_reached(self):
        res = r3_liquid(report(stages=stages_until("POSITION_VERIFIED")), DEFAULT_CONFIG)
        self.assertEqual(res.reason, R.LIQUID_NOT_ACCEPTED)


class TestR4Extraction(unittest.TestCase):
    def test_aborted_before_extraction(self):
        res = r4_extraction(report(stages=stages_until("LIQUID_ACCEPTED")), DEFAULT_CONFIG)
        self.assertEqual(res.reason, R.ABORTED_PRE_EXTRACTION)


class TestR5PostExtractionFault(unittest.TestCase):
    def fault(self, stage):
        return {"fault_code": "F-1", "stage": stage}

    def test_fault_before_extraction_is_ignored(self):
        self.assertTrue(r5_no_post_extraction_fault(
            report(faults=[self.fault("POSITION_VERIFIED")]), DEFAULT_CONFIG).passed)

    def test_fault_at_extraction_fails(self):
        res = r5_no_post_extraction_fault(report(faults=[self.fault("EXTRACTED")]), DEFAULT_CONFIG)
        self.assertEqual(res.reason, R.POST_EXTRACTION_FAULT)

    def test_fault_at_retraction_fails(self):
        res = r5_no_post_extraction_fault(report(faults=[self.fault("RETRACTED")]), DEFAULT_CONFIG)
        self.assertEqual(res.reason, R.POST_EXTRACTION_FAULT)

    def test_fault_at_completed_is_ignored(self):
        self.assertTrue(r5_no_post_extraction_fault(
            report(faults=[self.fault("COMPLETED")]), DEFAULT_CONFIG).passed)

    def test_stageless_fault_after_extraction_fails(self):
        res = r5_no_post_extraction_fault(report(faults=[{"fault_code": "F-1"}]), DEFAULT_CONFIG)
        self.assertEqual(res.reason, R.POST_EXTRACTION_FAULT)

    def test_stageless_fault_without_extraction_is_ignored(self):
        r = report(stages=stages_until("LIQUID_ACCEPTED"), faults=[{"fault_code": "F-1"}])
        self.assertTrue(r5_no_post_extraction_fault(r, DEFAULT_CONFIG).passed)


class TestR6Completion(unittest.TestCase):
    def test_missing_stage(self):
        data = raw()
        del data["stages"][7]  # RETRACTED
        self.assertEqual(r6_completion(report(data), DEFAULT_CONFIG).reason, R.STAGE_SEQUENCE_INVALID)

    def test_out_of_order(self):
        data = raw()
        data["stages"][5], data["stages"][6] = data["stages"][6], data["stages"][5]
        self.assertEqual(r6_completion(report(data), DEFAULT_CONFIG).reason, R.STAGE_SEQUENCE_INVALID)

    def test_duplicate_stage(self):
        data = raw()
        data["stages"].insert(5, copy.deepcopy(data["stages"][4]))
        self.assertEqual(r6_completion(report(data), DEFAULT_CONFIG).reason, R.STAGE_SEQUENCE_INVALID)


class TestR7Timestamps(unittest.TestCase):
    def test_missing_timestamp(self):
        data = raw()
        data["stages"][6]["timestamp"] = None
        self.assertEqual(r7_timestamps(report(data), DEFAULT_CONFIG).reason, R.MISSING_TIMESTAMP)

    def test_time_goes_backwards(self):
        data = raw()
        data["stages"][6]["timestamp"] = "2026-10-20T15:00:10Z"  # SANITIZED before EXTRACTED
        self.assertEqual(r7_timestamps(report(data), DEFAULT_CONFIG).reason, R.TIMESTAMP_ORDER_INVALID)

    def test_equal_timestamps_allowed(self):
        data = raw()
        data["stages"][1]["timestamp"] = data["stages"][0]["timestamp"]
        self.assertTrue(r7_timestamps(report(data), DEFAULT_CONFIG).passed)


class TestR8Volume(unittest.TestCase):
    def test_no_volume(self):
        self.assertEqual(r8_volume(report(volume=None), DEFAULT_CONFIG).reason, R.VOLUME_MISSING)

    def test_no_validated_ml(self):
        self.assertEqual(r8_volume(with_volume(validated_ml=None), DEFAULT_CONFIG).reason, R.VOLUME_MISSING)

    def test_missing_secondary(self):
        self.assertEqual(r8_volume(with_volume(secondary_ml=None), DEFAULT_CONFIG).reason, R.VOLUME_MISSING)

    def test_mismatch(self):
        r = with_volume(primary_ml=250.0, secondary_ml=220.0, validated_ml=235.0)
        self.assertEqual(r8_volume(r, DEFAULT_CONFIG).reason, R.VOLUME_MISMATCH)

    def test_exactly_at_absolute_tolerance_passes(self):
        # 5.0 mL apart; 2% of 250 = 5.0 mL, so both limits are met exactly.
        r = with_volume(primary_ml=250.4, secondary_ml=245.4, validated_ml=250.0)
        self.assertTrue(r8_volume(r, DEFAULT_CONFIG).passed)

    def test_just_over_absolute_tolerance_fails(self):
        r = with_volume(primary_ml=250.5, secondary_ml=245.4, validated_ml=250.0)
        self.assertEqual(r8_volume(r, DEFAULT_CONFIG).reason, R.VOLUME_MISMATCH)

    def test_percentage_limit_applies_to_small_volumes(self):
        # 3 mL apart is within 5 mL, but over 2% of 100 mL (= 2 mL).
        r = with_volume(primary_ml=101.5, secondary_ml=98.5, validated_ml=100.0)
        self.assertEqual(r8_volume(r, DEFAULT_CONFIG).reason, R.VOLUME_MISMATCH)

    def test_exactly_at_percentage_limit_passes(self):
        # 2% of 53.3 mL = 1.066 mL; float math must not push the limit below that.
        for validated in (53.3, 53.8, 101.7, 187.9):
            with self.subTest(validated_ml=validated):
                limit = round(validated * 2 / 100, 6)
                r = with_volume(primary_ml=round(100 + limit, 6), secondary_ml=100.0,
                                validated_ml=validated)
                self.assertTrue(r8_volume(r, DEFAULT_CONFIG).passed)

    def test_low_confidence(self):
        self.assertEqual(r8_volume(with_volume(confidence=0.5), DEFAULT_CONFIG).reason,
                         R.VOLUME_LOW_CONFIDENCE)

    def test_missing_confidence(self):
        self.assertEqual(r8_volume(with_volume(confidence=None), DEFAULT_CONFIG).reason,
                         R.VOLUME_LOW_CONFIDENCE)

    def test_confidence_at_threshold_passes(self):
        self.assertTrue(r8_volume(with_volume(confidence=0.90), DEFAULT_CONFIG).passed)

    def test_thresholds_come_from_config(self):
        strict = VerificationConfig(min_volume_confidence=0.99)
        self.assertEqual(r8_volume(report(), strict).reason, R.VOLUME_LOW_CONFIDENCE)


class TestR9Sanitation(unittest.TestCase):
    def test_incomplete(self):
        r = report(sanitation={"completed": False, "fluid_ml": 10.0})
        self.assertEqual(r9_sanitation(r, DEFAULT_CONFIG).reason, R.SANITATION_INCOMPLETE)

    def test_not_reported(self):
        self.assertEqual(r9_sanitation(report(sanitation=None), DEFAULT_CONFIG).reason,
                         R.SANITATION_INCOMPLETE)


class TestDecideState(unittest.TestCase):
    def fail(self, reason):
        return RuleResult(rule_id="X", passed=False, reason=reason)

    def test_all_pass_is_verified(self):
        self.assertEqual(decide_state([RuleResult(rule_id="X", passed=True)]), S.VERIFIED)

    def test_precedence(self):
        self.assertEqual(decide_state([self.fail(R.VOLUME_MISMATCH), self.fail(R.ACCOUNT_MISSING)]),
                         S.REJECTED)
        self.assertEqual(decide_state([self.fail(R.SANITATION_INCOMPLETE),
                                       self.fail(R.POST_EXTRACTION_FAULT)]), S.FAULTED)
        self.assertEqual(decide_state([self.fail(R.MISSING_TIMESTAMP)]), S.UNVERIFIED)


class TestEvaluate(unittest.TestCase):
    def test_happy_path(self):
        e = evaluate(report(), NOW)
        self.assertEqual(e.state, S.VERIFIED)
        self.assertEqual(e.reasons, [])
        self.assertEqual(len(e.rule_results), 9)
        self.assertEqual(e.event_id, derive_event_id("ST-01", "C-HAPPY-001"))
        self.assertEqual(e.deposit_volume_ml, 250.1)
        self.assertEqual(e.sanitation_fluid_ml, 30.0)  # separate, never added to the deposit
        self.assertEqual(e.cycle_started_at, datetime(2026, 10, 20, 15, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(e.cycle_completed_at, datetime(2026, 10, 20, 15, 0, 32, tzinfo=timezone.utc))
        self.assertEqual(len(e.stage_timestamps), 9)
        self.assertEqual(e.created_at, NOW)
        self.assertEqual(e.source_payload_hash, payload_hash(report()))

    def test_rejected_has_no_deposit(self):
        e = evaluate(report(account_id=None), NOW)
        self.assertEqual(e.state, S.REJECTED)
        self.assertEqual(e.reasons, [R.ACCOUNT_MISSING])
        self.assertIsNone(e.deposit_volume_ml)

    def test_unverified_keeps_deposit(self):
        e = evaluate(report(sanitation={"completed": False}), NOW)
        self.assertEqual(e.state, S.UNVERIFIED)
        self.assertEqual(e.deposit_volume_ml, 250.1)

    def test_all_reasons_recorded_in_rule_order(self):
        r = report(account_id=None, volume={**raw()["volume"], "secondary_ml": 200.0})
        e = evaluate(r, NOW)
        self.assertEqual(e.state, S.REJECTED)
        self.assertEqual(e.reasons, [R.ACCOUNT_MISSING, R.VOLUME_MISMATCH])

    def test_aborted_pre_extraction(self):
        e = evaluate(report(stages=stages_until("LIQUID_ACCEPTED"), volume=None, sanitation=None), NOW)
        self.assertEqual(e.state, S.REJECTED)
        self.assertEqual(e.reasons, [R.ABORTED_PRE_EXTRACTION, R.STAGE_SEQUENCE_INVALID,
                                     R.VOLUME_MISSING, R.SANITATION_INCOMPLETE])
        self.assertIsNone(e.cycle_completed_at)

    def test_post_extraction_fault(self):
        r = report(stages=stages_until("VOLUME_VALIDATED"), sanitation=None,
                   faults=[{"fault_code": "PUMP_STALL", "stage": "VOLUME_VALIDATED"}])
        e = evaluate(r, NOW)
        self.assertEqual(e.state, S.FAULTED)
        self.assertEqual(e.reasons[0], R.POST_EXTRACTION_FAULT)
        self.assertEqual(e.deposit_volume_ml, 250.1)

    def test_retry_then_success(self):
        r = report(retry_count=2, faults=[{"fault_code": "POS_RETRY", "stage": "POSITION_VERIFIED",
                                           "retryable": True}])
        e = evaluate(r, NOW)
        self.assertEqual(e.state, S.VERIFIED)
        self.assertEqual(e.retry_count, 2)

    def test_deterministic(self):
        self.assertEqual(evaluate(report(), NOW).model_dump(), evaluate(report(), NOW).model_dump())

    def test_stage_timestamps_serialize_as_strings(self):
        dumped = evaluate(report(), NOW).model_dump(mode="json")
        self.assertEqual(dumped["stage_timestamps"][CycleStage.DETECTED.value], "2026-10-20T15:00:00.000Z")


if __name__ == "__main__":
    unittest.main()
