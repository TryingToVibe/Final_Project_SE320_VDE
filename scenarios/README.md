# Scenarios  (OWNER: Teammate B)

One JSON file per scenario. `tests/test_scenarios.py` loads every `*.json` here,
runs `report` through `vde.rules.evaluate`, and checks the result against `expected`.
Team 5 can reuse these files to test our logic.

## File format

```json
{
  "name": "account_missing",
  "description": "One sentence: what happened at the station.",
  "report":   { ...a complete CycleReport... },
  "expected": {
    "state": "REJECTED",
    "reasons": ["ACCOUNT_MISSING"],
    "deposit_volume_ml": null
  }
}
```

* `report` must be a valid CycleReport. The test runner checks this.
* `expected.reasons` lists **every** reason, in rule order (R1 to R9).
* `expected.deposit_volume_ml` is optional; include it when it matters.
  It is `null` for REJECTED (nothing deposited) and when no `validated_ml` was
  reported; otherwise it equals `volume.validated_ml` (never plus sanitation fluid).
* Every scenario uses its own `cycle_id`, so all of them can be submitted to one
  store without colliding.
* Copy `happy_path.json` and change only what the scenario needs.

## What the test runner checks

| Runs | Check |
|---|---|
| Today | Every file is well formed and `report` is a valid CycleReport |
| Today | `expected.state` follows precedence REJECTED > FAULTED > UNVERIFIED > VERIFIED for the listed reasons |
| Today | `expected.reasons` are in R1..R9 order, with no duplicates and at most one per rule |
| Today | `expected.deposit_volume_ml` follows the rule above |
| Today | Every required scenario exists; every `ReasonCode` and every terminal state is exercised |
| Once `evaluate()` exists | Actual state, reasons and deposit volume match `expected` |
| Once `evaluate()` exists | `event_id`, identity fields, faults, `retry_count`, `created_at`, 9 `rule_results`, separate `sanitation_fluid_ml` |
| Once `evaluate()` exists | Same report evaluated twice gives an identical event |

The outcome checks are **skipped** (not failed) until Teammate A finishes `vde/rules.py`.

## Scenarios

Required by the project brief and STATE_MODEL.md section 6:

| File | Change from happy path | Expected |
|---|---|---|
| `happy_path.json` | — | VERIFIED |
| `identity_failure.json` | no `receptacle_id`, IDENTIFIED `passed: false` | REJECTED / IDENTITY_FAILURE |
| `account_missing.json` | no `account_id` | REJECTED / ACCOUNT_MISSING |
| `aborted_pre_extraction.json` | stages stop after LIQUID_ACCEPTED, no volume/sanitation | REJECTED / ABORTED_PRE_EXTRACTION, STAGE_SEQUENCE_INVALID, VOLUME_MISSING, SANITATION_INCOMPLETE |
| `liquid_not_accepted.json` | LIQUID_ACCEPTED `passed: false`, stops there | REJECTED / LIQUID_NOT_ACCEPTED, ABORTED_PRE_EXTRACTION, STAGE_SEQUENCE_INVALID, VOLUME_MISSING, SANITATION_INCOMPLETE |
| `volume_mismatch.json` | primary 250, secondary 220, validated 235 | UNVERIFIED / VOLUME_MISMATCH |
| `volume_low_confidence.json` | confidence 0.5 | UNVERIFIED / VOLUME_LOW_CONFIDENCE |
| `sanitation_incomplete.json` | `sanitation.completed: false`, 12 mL fluid | UNVERIFIED / SANITATION_INCOMPLETE |
| `post_extraction_fault.json` | fault at VOLUME_VALIDATED, stages stop there, no volume/sanitation | FAULTED / POST_EXTRACTION_FAULT, STAGE_SEQUENCE_INVALID, VOLUME_MISSING, SANITATION_INCOMPLETE |
| `missing_timestamp.json` | RETRACTED `timestamp: null` | UNVERIFIED / MISSING_TIMESTAMP |
| `timestamps_out_of_order.json` | SANITIZED earlier than EXTRACTED | UNVERIFIED / TIMESTAMP_ORDER_INVALID |
| `multiple_failures.json` | no account AND volume mismatch | REJECTED / ACCOUNT_MISSING, VOLUME_MISMATCH |
| `retry_then_success.json` | `retry_count: 2`, two retryable faults at POSITION_VERIFIED | VERIFIED |

Extra scenarios, so every reason code and terminal state is covered:

| File | Change from happy path | Expected |
|---|---|---|
| `volume_missing.json` | no `volume` | UNVERIFIED / VOLUME_MISSING |
| `stage_skipped.json` | POSITION_VERIFIED stage removed | UNVERIFIED / STAGE_SEQUENCE_INVALID |
| `retraction_fault.json` | fault at RETRACTED, no COMPLETED; volume and sanitation fine | FAULTED / POST_EXTRACTION_FAULT, STAGE_SEQUENCE_INVALID (deposit 250.1 kept) |

## Reason code coverage

| Reason | Rule | State | Scenarios |
|---|---|---|---|
| IDENTITY_FAILURE | R1 | REJECTED | identity_failure |
| ACCOUNT_MISSING | R2 | REJECTED | account_missing, multiple_failures |
| LIQUID_NOT_ACCEPTED | R3 | REJECTED | liquid_not_accepted |
| ABORTED_PRE_EXTRACTION | R4 | REJECTED | aborted_pre_extraction, liquid_not_accepted |
| POST_EXTRACTION_FAULT | R5 | FAULTED | post_extraction_fault, retraction_fault |
| STAGE_SEQUENCE_INVALID | R6 | UNVERIFIED | stage_skipped (+ every early-stopping scenario) |
| MISSING_TIMESTAMP | R7 | UNVERIFIED | missing_timestamp |
| TIMESTAMP_ORDER_INVALID | R7 | UNVERIFIED | timestamps_out_of_order |
| VOLUME_MISSING | R8 | UNVERIFIED | volume_missing (+ early-stopping scenarios) |
| VOLUME_MISMATCH | R8 | UNVERIFIED | volume_mismatch, multiple_failures |
| VOLUME_LOW_CONFIDENCE | R8 | UNVERIFIED | volume_low_confidence |
| SANITATION_INCOMPLETE | R9 | UNVERIFIED | sanitation_incomplete (+ early-stopping scenarios) |

## Assumptions (confirm with Teammate A / team lead)

* R4 only checks that EXTRACTED is present; R6 checks presence and order, not `passed`.
* R5 treats a fault with no `stage` as post-extraction if EXTRACTED was reached
  (it cannot be placed earlier), and ignores it otherwise; a retryable fault
  before EXTRACTED does not block VERIFIED.
* R7 reports MISSING_TIMESTAMP before checking order (one reason per rule).
* R8 checks missing, then mismatch, then confidence (one reason per rule).

Duplicate-submission scenarios (same report twice; same cycle with changed
volume) belong in `tests/test_service.py`, since they test storage, not rules.
