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
* Copy `happy_path.json` and change only what the scenario needs.

## Required scenarios (from the project brief and STATE_MODEL.md §6)

| File | Change from happy path | Expected |
|---|---|---|
| `happy_path.json` | (done) | VERIFIED |
| `identity_failure.json` | no `receptacle_id`, IDENTIFIED `passed: false` | REJECTED / IDENTITY_FAILURE |
| `account_missing.json` | no `account_id` | REJECTED / ACCOUNT_MISSING |
| `aborted_pre_extraction.json` | stages stop after LIQUID_ACCEPTED, no volume/sanitation | REJECTED / ABORTED_PRE_EXTRACTION (+ others; work them out) |
| `liquid_not_accepted.json` | LIQUID_ACCEPTED `passed: false`, stops there | REJECTED |
| `volume_mismatch.json` | primary 250, secondary 220 | UNVERIFIED / VOLUME_MISMATCH |
| `volume_low_confidence.json` | confidence 0.5 | UNVERIFIED / VOLUME_LOW_CONFIDENCE |
| `sanitation_incomplete.json` | `sanitation.completed: false` | UNVERIFIED / SANITATION_INCOMPLETE |
| `post_extraction_fault.json` | fault at VOLUME_VALIDATED, stages stop there | FAULTED (+ others) |
| `missing_timestamp.json` | one stage with no timestamp | UNVERIFIED / MISSING_TIMESTAMP |
| `timestamps_out_of_order.json` | SANITIZED earlier than EXTRACTED | UNVERIFIED / TIMESTAMP_ORDER_INVALID |
| `multiple_failures.json` | no account AND volume mismatch | REJECTED (precedence), both reasons listed |
| `retry_then_success.json` | `retry_count: 2`, recoverable fault before extraction | VERIFIED |

Duplicate-submission scenarios (same report twice; same cycle with changed
volume) belong in `tests/test_service.py`, since they test storage, not rules.
