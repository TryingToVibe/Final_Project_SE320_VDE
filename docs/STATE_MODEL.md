# Verified Disposal Event — State Model (v0.1.0, draft)

## 1. Purpose

A **Verified Disposal Event** is a trusted record that a specific, authorized account deposited a defensible volume of liquid at a specific station and receptacle, and that the full cycle (including sanitation) finished. This component decides whether a processing cycle earns that status. It never controls hardware.

## 2. Two separate concepts

| Concept | Owner | Values |
|---|---|---|
| **Cycle stage** — the physical step the station reached | Team 2 (input) | `DETECTED → IDENTIFIED → POSITION_VERIFIED → LIQUID_ACCEPTED → EXTRACTED → VOLUME_VALIDATED → SANITIZED → RETRACTED → COMPLETED` |
| **Event state** — our verdict about the cycle | This team (output) | `ATTEMPTED, IN_PROGRESS, COMPLETED, VERIFIED, UNVERIFIED, REJECTED, FAULTED` |

## 3. Event states

| State | Meaning | Terminal? |
|---|---|---|
| `ATTEMPTED` | Receptacle presented/detected. Nothing proven. | No |
| `IN_PROGRESS` | Receptacle identified, account authorized, cycle under way. | No |
| `COMPLETED` | Physical cycle finished; verification rules not yet applied. | No |
| `VERIFIED` | Every verification rule passed. **The only state downstream may treat as a successful disposal.** | Yes |
| `UNVERIFIED` | Cycle finished, but a rule failed (volume, sanitation, timestamps). A deposit probably occurred but cannot be vouched for. | Yes |
| `REJECTED` | Stopped **before extraction**. No liquid was deposited. | Yes |
| `FAULTED` | Fault **after extraction** but before completion. Liquid was taken; the cycle did not finish cleanly. | Yes |

**Key distinction:** `REJECTED` = *no deposit happened*. `UNVERIFIED`/`FAULTED` = *a deposit happened but cannot be trusted*. Environmental records and fault handling need this difference.

## 4. Allowed transitions

```
ATTEMPTED ──► IN_PROGRESS ──► COMPLETED ──► VERIFIED
    │              │              └───────► UNVERIFIED
    │              ├──► FAULTED
    └──────────────┴──► REJECTED
```

| From | Allowed to |
|---|---|
| ATTEMPTED | IN_PROGRESS, REJECTED |
| IN_PROGRESS | COMPLETED, REJECTED, FAULTED |
| COMPLETED | VERIFIED, UNVERIFIED |
| any terminal | *(none — terminal events are immutable)* |

`ATTEMPTED` and `IN_PROGRESS` can never move straight to `VERIFIED`. A partial cycle cannot masquerade as a successful one.

## 5. Conditions required for VERIFIED

All of the following must hold (implemented as rules in step 2):

| Rule | Condition | Failure reason → state |
|---|---|---|
| R1 Identity | `receptacle_id` present and valid | `IDENTITY_FAILURE` → REJECTED |
| R2 Account | authorized `account_id` present (**required for every disposal**) | `ACCOUNT_MISSING` → REJECTED |
| R3 Liquid | `LIQUID_ACCEPTED` stage passed | `LIQUID_NOT_ACCEPTED` → REJECTED |
| R4 Extraction | `EXTRACTED` stage reached | `ABORTED_PRE_EXTRACTION` → REJECTED |
| R5 No post-extraction fault | no fault at/after `EXTRACTED` before `COMPLETED` | `POST_EXTRACTION_FAULT` → FAULTED |
| R6 Completion | all 9 stages present, in order | `STAGE_SEQUENCE_INVALID` → UNVERIFIED |
| R7 Timestamps | every stage has a timestamp, non-decreasing | `MISSING_TIMESTAMP` / `TIMESTAMP_ORDER_INVALID` → UNVERIFIED |
| R8 Volume | validated volume present; two measurements agree within tolerance; confidence ≥ threshold | `VOLUME_MISSING` / `VOLUME_MISMATCH` / `VOLUME_LOW_CONFIDENCE` → UNVERIFIED |
| R9 Sanitation | sanitation reported complete | `SANITATION_INCOMPLETE` → UNVERIFIED |

**Precedence when several rules fail:** REJECTED > FAULTED > UNVERIFIED. All failing reasons are still recorded in `reasons`, so nothing is hidden.

## 6. Edge cases → expected outcome

| Edge case | State | Reason |
|---|---|---|
| RFID/identity failure | REJECTED | IDENTITY_FAILURE |
| No account associated | REJECTED | ACCOUNT_MISSING |
| Cycle aborted before extraction | REJECTED | ABORTED_PRE_EXTRACTION |
| Volume measurements disagree beyond tolerance | UNVERIFIED | VOLUME_MISMATCH |
| Sanitation incomplete | UNVERIFIED | SANITATION_INCOMPLETE |
| Fault after extraction, before completion | FAULTED | POST_EXTRACTION_FAULT |
| Missing required timestamp | UNVERIFIED | MISSING_TIMESTAMP |
| Missing station_id / cycle_id | *no event* — HTTP 422 | cannot attribute the report |
| Duplicate completion message | *no new event* — return existing | — |

## 7. Identity and idempotency

- `event_id = UUIDv5(VDE_NAMESPACE, "{station_id}:{cycle_id}")`, so it is deterministic.
- Same cycle, identical payload → return the existing event (HTTP 200).
- Same cycle, *different* payload → HTTP 409 `EVENT_CONFLICT`; the stored event is never overwritten.
- Comparison uses `source_payload_hash` (SHA-256 of the canonical report).
- *Assumption:* Team 2 provides a `cycle_id` unique per station. If that changes, only `vde/identity.py` changes.

## 8. Proposed cross-team conventions (to confirm)

| Item | Proposal |
|---|---|
| Timestamps | ISO 8601, UTC, milliseconds, `Z` suffix: `2026-10-07T19:46:00.123Z`. Naive timestamps refused. |
| Volume units | mL, non-negative number |
| Identifiers | `^[A-Za-z0-9_-]{1,64}$` |
| Field names | snake_case; enum values UPPER_SNAKE_CASE |
| Unknown fields | refused (catches misspelled field names) |
| Versioning | `schema_version` semver in every payload; MAJOR bump = breaking change |
| Errors | `{"error": {"code", "message", "details"}, "schema_version"}` |

## 9. Open questions

1. Volume tolerance: absolute (± mL), relative (± %), or both? Who sets it — us or Team 1?
2. Minimum volume confidence threshold?
3. Does Team 6 classify some post-extraction faults as harmless (e.g. retraction slow but completed)?
4. Does Team 2 send one report at cycle end, or stream stage updates? (The state machine supports both.)
5. Are fault codes free text or an enum from Team 6?
