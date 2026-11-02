"""Rules engine: turns a CycleReport into a DisposalEvent.        OWNER: Teammate A

Contract (do not change signatures without telling the team lead):

    evaluate(report, now, config=DEFAULT_CONFIG) -> DisposalEvent

Requirements:
  * DETERMINISTIC: same (report, now, config) -> identical event. No reading the
    clock, no randomness, no database. `now` is passed in and becomes created_at.
  * Run EVERY rule and record every RuleResult, even after one fails, so the
    event explains all of its problems (traceability).
  * Final state by precedence: any REJECTED-reason  -> REJECTED
                               else any FAULTED     -> FAULTED
                               else any UNVERIFIED  -> UNVERIFIED
                               else                 -> VERIFIED
  * deposit_volume_ml comes from volume.validated_ml ONLY. Never add sanitation fluid.
  * Thresholds come from `config` (vde/config.py), never hard-coded numbers.

See docs/STATE_MODEL.md section 5 for the full rule table.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from .config import DEFAULT_CONFIG, VerificationConfig
from .enums import STAGE_ORDER, CycleStage, EventState, ReasonCode
from .identity import derive_event_id, payload_hash
from .models import CycleReport, DisposalEvent, RuleResult

Rule = Callable[[CycleReport, VerificationConfig], RuleResult]

# Which terminal state each reason forces. Used by decide_state().
REASON_STATE: dict[ReasonCode, EventState] = {
    ReasonCode.IDENTITY_FAILURE: EventState.REJECTED,
    ReasonCode.ACCOUNT_MISSING: EventState.REJECTED,
    ReasonCode.ABORTED_PRE_EXTRACTION: EventState.REJECTED,
    ReasonCode.LIQUID_NOT_ACCEPTED: EventState.REJECTED,
    ReasonCode.POST_EXTRACTION_FAULT: EventState.FAULTED,
    ReasonCode.VOLUME_MISSING: EventState.UNVERIFIED,
    ReasonCode.VOLUME_MISMATCH: EventState.UNVERIFIED,
    ReasonCode.VOLUME_LOW_CONFIDENCE: EventState.UNVERIFIED,
    ReasonCode.SANITATION_INCOMPLETE: EventState.UNVERIFIED,
    ReasonCode.MISSING_TIMESTAMP: EventState.UNVERIFIED,
    ReasonCode.STAGE_SEQUENCE_INVALID: EventState.UNVERIFIED,
    ReasonCode.TIMESTAMP_ORDER_INVALID: EventState.UNVERIFIED,
}


def _ok(rule_id: str) -> RuleResult:
    return RuleResult(rule_id=rule_id, passed=True)


def _fail(rule_id: str, reason: ReasonCode, detail: str) -> RuleResult:
    return RuleResult(rule_id=rule_id, passed=False, reason=reason, detail=detail)


def _stage(report: CycleReport, stage: CycleStage):
    """Return the StageRecord for `stage`, or None if the station never reported it."""
    return next((s for s in report.stages if s.stage == stage), None)


# ----------------------------------------------------------------- the 9 rules
# WORKED EXAMPLE: follow this pattern for R2-R9.

def r1_identity(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R1: receptacle must be identified (IDENTIFIED stage passed, receptacle_id present)."""
    if not report.receptacle_id:
        return _fail("R1_IDENTITY", ReasonCode.IDENTITY_FAILURE, "receptacle_id missing")
    identified = _stage(report, CycleStage.IDENTIFIED)
    if identified is not None and not identified.passed:
        return _fail("R1_IDENTITY", ReasonCode.IDENTITY_FAILURE, "IDENTIFIED stage reported failure")
    return _ok("R1_IDENTITY")


def r2_account(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R2: account_id present. Fail -> ACCOUNT_MISSING."""
    if not report.account_id:
        return _fail("R2_ACCOUNT", ReasonCode.ACCOUNT_MISSING, "account_id missing")
    return _ok("R2_ACCOUNT")


def r3_liquid(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R3: LIQUID_ACCEPTED stage present AND passed. Fail -> LIQUID_NOT_ACCEPTED."""
    liquid = _stage(report, CycleStage.LIQUID_ACCEPTED)
    if liquid is None:
        return _fail("R3_LIQUID", ReasonCode.LIQUID_NOT_ACCEPTED, "LIQUID_ACCEPTED stage not reached")
    if not liquid.passed:
        return _fail("R3_LIQUID", ReasonCode.LIQUID_NOT_ACCEPTED, "LIQUID_ACCEPTED stage reported failure")
    return _ok("R3_LIQUID")


def r4_extraction(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R4: EXTRACTED stage reached. Fail -> ABORTED_PRE_EXTRACTION."""
    if _stage(report, CycleStage.EXTRACTED) is None:
        return _fail("R4_EXTRACTION", ReasonCode.ABORTED_PRE_EXTRACTION, "EXTRACTED stage not reached")
    return _ok("R4_EXTRACTION")


def r5_no_post_extraction_fault(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R5: no fault whose stage is EXTRACTED or later (before COMPLETED).
    Hint: compare positions in enums.STAGE_ORDER. Fail -> POST_EXTRACTION_FAULT.
    Open question 3: Team 6 may mark some faults as harmless.

    A fault with no stage cannot be placed in the cycle. If extraction happened,
    we cannot rule out that it came after, so it is treated as post-extraction.
    """
    extracted = STAGE_ORDER.index(CycleStage.EXTRACTED)
    completed = STAGE_ORDER.index(CycleStage.COMPLETED)
    reached_extraction = _stage(report, CycleStage.EXTRACTED) is not None
    for fault in report.faults:
        if fault.stage is None:
            if reached_extraction:
                return _fail("R5_NO_POST_EXTRACTION_FAULT", ReasonCode.POST_EXTRACTION_FAULT,
                             f"fault {fault.fault_code} has no stage and extraction occurred")
            continue
        if extracted <= STAGE_ORDER.index(fault.stage) < completed:
            return _fail("R5_NO_POST_EXTRACTION_FAULT", ReasonCode.POST_EXTRACTION_FAULT,
                         f"fault {fault.fault_code} at {fault.stage.value}")
    return _ok("R5_NO_POST_EXTRACTION_FAULT")


def r6_completion(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R6: all 9 stages present, each exactly once, in STAGE_ORDER. Fail -> STAGE_SEQUENCE_INVALID."""
    reported = [s.stage for s in report.stages]
    if reported != list(STAGE_ORDER):
        return _fail("R6_COMPLETION", ReasonCode.STAGE_SEQUENCE_INVALID,
                     "stages reported: " + ", ".join(s.value for s in reported))
    return _ok("R6_COMPLETION")


def r7_timestamps(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R7: every stage has a timestamp (else MISSING_TIMESTAMP) and they never
    decrease in stage order (else TIMESTAMP_ORDER_INVALID)."""
    missing = [s.stage.value for s in report.stages if s.timestamp is None]
    if missing:
        return _fail("R7_TIMESTAMPS", ReasonCode.MISSING_TIMESTAMP,
                     "no timestamp for: " + ", ".join(missing))
    # Compare in canonical stage order, so the check is independent of R6.
    ordered = sorted(report.stages, key=lambda s: STAGE_ORDER.index(s.stage))
    for prev, cur in zip(ordered, ordered[1:]):
        if cur.timestamp < prev.timestamp:
            return _fail("R7_TIMESTAMPS", ReasonCode.TIMESTAMP_ORDER_INVALID,
                         f"{cur.stage.value} is earlier than {prev.stage.value}")
    return _ok("R7_TIMESTAMPS")


def r8_volume(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R8: volume and volume.validated_ml present (else VOLUME_MISSING);
    |primary_ml - secondary_ml| within config tolerances (else VOLUME_MISMATCH);
    confidence >= config.min_volume_confidence (else VOLUME_LOW_CONFIDENCE).

    Agreement and confidence cannot be checked without both measurements and a
    confidence value, so their absence fails rather than passes.
    """
    vol = report.volume
    if vol is None or vol.validated_ml is None:
        return _fail("R8_VOLUME", ReasonCode.VOLUME_MISSING, "validated_ml missing")
    if vol.primary_ml is None or vol.secondary_ml is None:
        return _fail("R8_VOLUME", ReasonCode.VOLUME_MISSING,
                     "primary_ml and secondary_ml are both required to check agreement")
    # Round away float noise (e.g. 250.4 - 245.4 = 5.000000000000028).
    diff = round(abs(vol.primary_ml - vol.secondary_ml), 6)
    # Round the limit the same way, or e.g. 2% of 53.3 comes out a hair under 1.066.
    pct_limit = round(vol.validated_ml * config.volume_tolerance_pct / 100, 6)
    if diff > config.volume_tolerance_ml or diff > pct_limit:
        return _fail("R8_VOLUME", ReasonCode.VOLUME_MISMATCH,
                     f"measurements differ by {diff} mL (limits {config.volume_tolerance_ml} mL, "
                     f"{config.volume_tolerance_pct}% = {pct_limit:.3f} mL)")
    if vol.confidence is None or vol.confidence < config.min_volume_confidence:
        return _fail("R8_VOLUME", ReasonCode.VOLUME_LOW_CONFIDENCE,
                     f"confidence {vol.confidence} below {config.min_volume_confidence}")
    return _ok("R8_VOLUME")


def r9_sanitation(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R9: sanitation present and completed is True. Fail -> SANITATION_INCOMPLETE."""
    if report.sanitation is None:
        return _fail("R9_SANITATION", ReasonCode.SANITATION_INCOMPLETE, "sanitation not reported")
    if not report.sanitation.completed:
        return _fail("R9_SANITATION", ReasonCode.SANITATION_INCOMPLETE, "sanitation reported incomplete")
    return _ok("R9_SANITATION")


RULES: list[Rule] = [
    r1_identity, r2_account, r3_liquid, r4_extraction, r5_no_post_extraction_fault,
    r6_completion, r7_timestamps, r8_volume, r9_sanitation,
]


# ------------------------------------------------------------------ decisions

def decide_state(results: list[RuleResult]) -> EventState:
    """Apply precedence REJECTED > FAULTED > UNVERIFIED > VERIFIED (see module docstring)."""
    forced = {REASON_STATE[r.reason] for r in results if not r.passed}
    for state in (EventState.REJECTED, EventState.FAULTED, EventState.UNVERIFIED):
        if state in forced:
            return state
    return EventState.VERIFIED


def evaluate(
    report: CycleReport,
    now: datetime,
    config: VerificationConfig = DEFAULT_CONFIG,
) -> DisposalEvent:
    """Run all RULES on `report` and build the resulting DisposalEvent.

    Fill in: event_id (identity.derive_event_id), state (decide_state), reasons
    (every failing rule's reason, no duplicates, in rule order), rule_results,
    the identity fields copied from the report, deposit_volume_ml (only when the
    event is VERIFIED, UNVERIFIED or FAULTED and validated_ml exists),
    sanitation_fluid_ml, stage_timestamps, cycle_started_at (DETECTED time),
    cycle_completed_at (COMPLETED time), faults, retry_count, created_at=now,
    source_payload_hash (identity.payload_hash).
    """
    results = [rule(report, config) for rule in RULES]
    state = decide_state(results)

    reasons: list[ReasonCode] = []
    for r in results:
        if not r.passed and r.reason not in reasons:
            reasons.append(r.reason)

    # REJECTED means nothing was deposited, so no deposit volume is reported.
    # Sanitation fluid is never added to the deposit.
    deposit = None
    if state != EventState.REJECTED and report.volume is not None:
        deposit = report.volume.validated_ml

    stage_timestamps = {s.stage: s.timestamp for s in report.stages}

    return DisposalEvent(
        event_id=derive_event_id(report.station_id, report.cycle_id),
        state=state,
        reasons=reasons,
        rule_results=results,
        station_id=report.station_id,
        cycle_id=report.cycle_id,
        receptacle_id=report.receptacle_id,
        account_id=report.account_id,
        deposit_volume_ml=deposit,
        sanitation_fluid_ml=report.sanitation.fluid_ml if report.sanitation else None,
        cycle_started_at=stage_timestamps.get(CycleStage.DETECTED),
        cycle_completed_at=stage_timestamps.get(CycleStage.COMPLETED),
        stage_timestamps=stage_timestamps,
        faults=report.faults,
        retry_count=report.retry_count,
        created_at=now,
        source_payload_hash=payload_hash(report),
    )
