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
from .enums import CycleStage, EventState, ReasonCode
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
    raise NotImplementedError("Teammate A")


def r3_liquid(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R3: LIQUID_ACCEPTED stage present AND passed. Fail -> LIQUID_NOT_ACCEPTED."""
    raise NotImplementedError("Teammate A")


def r4_extraction(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R4: EXTRACTED stage reached. Fail -> ABORTED_PRE_EXTRACTION."""
    raise NotImplementedError("Teammate A")


def r5_no_post_extraction_fault(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R5: no fault whose stage is EXTRACTED or later (before COMPLETED).
    Hint: compare positions in enums.STAGE_ORDER. Fail -> POST_EXTRACTION_FAULT.
    Open question 3: Team 6 may mark some faults as harmless."""
    raise NotImplementedError("Teammate A")


def r6_completion(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R6: all 9 stages present, each exactly once, in STAGE_ORDER. Fail -> STAGE_SEQUENCE_INVALID."""
    raise NotImplementedError("Teammate A")


def r7_timestamps(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R7: every stage has a timestamp (else MISSING_TIMESTAMP) and they never
    decrease in stage order (else TIMESTAMP_ORDER_INVALID)."""
    raise NotImplementedError("Teammate A")


def r8_volume(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R8: volume and volume.validated_ml present (else VOLUME_MISSING);
    |primary_ml - secondary_ml| within config tolerances (else VOLUME_MISMATCH);
    confidence >= config.min_volume_confidence (else VOLUME_LOW_CONFIDENCE)."""
    raise NotImplementedError("Teammate A")


def r9_sanitation(report: CycleReport, config: VerificationConfig) -> RuleResult:
    """R9: sanitation present and completed is True. Fail -> SANITATION_INCOMPLETE."""
    raise NotImplementedError("Teammate A")


RULES: list[Rule] = [
    r1_identity, r2_account, r3_liquid, r4_extraction, r5_no_post_extraction_fault,
    r6_completion, r7_timestamps, r8_volume, r9_sanitation,
]


# ------------------------------------------------------------------ decisions

def decide_state(results: list[RuleResult]) -> EventState:
    """Apply precedence REJECTED > FAULTED > UNVERIFIED > VERIFIED (see module docstring)."""
    raise NotImplementedError("Teammate A")


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
    raise NotImplementedError("Teammate A")
