"""Pydantic data models for the Verified Disposal Event (VDE) component.

Three groups of models:
  * CycleReport      -- INPUT: what Teams 1/2/6 send us about one processing cycle
  * DisposalEvent    -- OUTPUT: the event Teams 4/7 transport and ingest
  * ErrorResponse    -- shared error envelope for every API failure

Design rule for inputs: fields we need just to *attribute* a report
(station_id, cycle_id, schema_version) are hard-required, so a report without
them is refused (HTTP 422). Everything else is optional at the schema level so
that missing data produces a REJECTED / UNVERIFIED event with a reason code
instead of disappearing as a validation error. Missing data is information.

Conventions (proposed cross-team contract, see docs/STATE_MODEL.md):
  * timestamps: timezone-aware, serialized ISO 8601 UTC with ms, e.g. 2026-10-07T19:46:00.123Z
  * volumes: millilitres (mL), non-negative
  * field names: snake_case; enum values: UPPER_SNAKE_CASE
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    model_validator,
)

from .enums import CycleStage, EventState, ReasonCode

SCHEMA_VERSION = "0.1.0"  # semver; bump MAJOR on breaking changes to shared fields

# Identifier pattern: letters, digits, dash, underscore. (Proposed; confirm with teams.)
ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


def to_utc_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class _Base(BaseModel):
    # Reject unknown fields: a misspelled field name is a contract bug, not data.
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


# --------------------------------------------------------------------------- inputs

class StageRecord(_Base):
    stage: CycleStage
    timestamp: Optional[AwareDatetime] = Field(
        None, description="When the station reached this stage. Missing -> MISSING_TIMESTAMP."
    )
    passed: bool = Field(True, description="False if the station reports this stage's check failed.")

    @field_serializer("timestamp")
    def _ser_ts(self, v):
        return to_utc_iso(v)


class VolumeResult(_Base):
    """Deposit volume from Team 1's validated measurement. User deposit only."""

    primary_ml: Optional[float] = Field(None, ge=0, description="Measurement source A")
    secondary_ml: Optional[float] = Field(None, ge=0, description="Independent measurement source B")
    validated_ml: Optional[float] = Field(None, ge=0, description="Team 1's validated deposit volume")
    confidence: Optional[float] = Field(None, ge=0, le=1)


class SanitationResult(_Base):
    """Kept separate from VolumeResult so sanitation fluid is never counted as deposit."""

    completed: bool
    fluid_ml: Optional[float] = Field(None, ge=0)


class FaultRecord(_Base):
    """A fault reported by the station (codes defined by Team 6's fault model)."""

    fault_code: str = Field(..., min_length=1)
    stage: Optional[CycleStage] = Field(None, description="Stage at which the fault occurred")
    timestamp: Optional[AwareDatetime] = None
    retryable: bool = False
    message: Optional[str] = None

    @field_serializer("timestamp")
    def _ser_ts(self, v):
        return to_utc_iso(v)


class CycleReport(_Base):
    """INPUT: everything known about one station processing cycle."""

    schema_version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    station_id: str = Field(..., pattern=ID_PATTERN)
    cycle_id: str = Field(..., pattern=ID_PATTERN)
    reported_at: AwareDatetime

    receptacle_id: Optional[str] = Field(None, pattern=ID_PATTERN)
    account_id: Optional[str] = Field(None, pattern=ID_PATTERN)

    stages: list[StageRecord] = Field(default_factory=list)
    volume: Optional[VolumeResult] = None
    sanitation: Optional[SanitationResult] = None
    faults: list[FaultRecord] = Field(default_factory=list)
    retry_count: int = Field(0, ge=0)

    @field_serializer("reported_at")
    def _ser_ts(self, v):
        return to_utc_iso(v)


# -------------------------------------------------------------------------- outputs

class RuleResult(_Base):
    """Outcome of one verification rule, for traceability."""

    rule_id: str
    passed: bool
    reason: Optional[ReasonCode] = None
    detail: Optional[str] = None


class DisposalEvent(_Base):
    """OUTPUT: the event record consumed by Teams 4 and 7.

    Invariants (enforced below):
      * VERIFIED  -> no reasons, every rule passed, deposit_volume_ml present
      * any other terminal state -> at least one reason
      * deposit_volume_ml is the user deposit only; sanitation fluid is separate
    """

    event_id: str
    schema_version: str = SCHEMA_VERSION
    state: EventState
    reasons: list[ReasonCode] = Field(default_factory=list)
    rule_results: list[RuleResult] = Field(default_factory=list)

    station_id: str
    cycle_id: str
    receptacle_id: Optional[str] = None
    account_id: Optional[str] = None

    deposit_volume_ml: Optional[float] = Field(None, ge=0)
    sanitation_fluid_ml: Optional[float] = Field(None, ge=0)

    cycle_started_at: Optional[AwareDatetime] = None
    cycle_completed_at: Optional[AwareDatetime] = None
    stage_timestamps: dict[CycleStage, Optional[AwareDatetime]] = Field(default_factory=dict)
    faults: list[FaultRecord] = Field(default_factory=list)
    retry_count: int = 0

    created_at: AwareDatetime
    source_payload_hash: str = Field(
        ..., description="SHA-256 of the canonical CycleReport; detects conflicting resubmissions"
    )

    @field_serializer("cycle_started_at", "cycle_completed_at", "created_at")
    def _ser_ts(self, v):
        return to_utc_iso(v)

    @field_serializer("stage_timestamps")
    def _ser_stage_ts(self, v):
        return {k.value: to_utc_iso(ts) for k, ts in v.items()}

    @model_validator(mode="after")
    def _check_invariants(self):
        if self.state == EventState.VERIFIED:
            if self.reasons:
                raise ValueError("VERIFIED event must not carry failure reasons")
            if any(not r.passed for r in self.rule_results):
                raise ValueError("VERIFIED event must have every rule passing")
            if self.deposit_volume_ml is None:
                raise ValueError("VERIFIED event must have a deposit_volume_ml")
            if not self.account_id or not self.receptacle_id:
                raise ValueError("VERIFIED event must be attributed to an account and receptacle")
        elif self.state in (EventState.REJECTED, EventState.UNVERIFIED, EventState.FAULTED):
            if not self.reasons:
                raise ValueError(f"{self.state.value} event must carry at least one reason")
        return self


# --------------------------------------------------------------------------- errors

class ErrorDetail(_Base):
    code: str = Field(..., description="Stable UPPER_SNAKE_CASE code, e.g. EVENT_CONFLICT")
    message: str
    details: dict = Field(default_factory=dict)


class ErrorResponse(_Base):
    """Every non-2xx API response uses this envelope."""

    error: ErrorDetail
    schema_version: str = SCHEMA_VERSION
