"""Shared enumerations for the Verified Disposal Event (VDE) component.

These values are part of the cross-team contract. Spellings are UPPER_SNAKE_CASE
and must not be renamed without a versioned schema change agreed with
Teams 1, 2, 4, 5, 6 and 7.
"""
from enum import Enum


class EventState(str, Enum):
    """Lifecycle state of a disposal event (owned by this component)."""

    ATTEMPTED = "ATTEMPTED"      # receptacle presented / detected; nothing proven yet
    IN_PROGRESS = "IN_PROGRESS"  # identified + authorized, cycle under way
    COMPLETED = "COMPLETED"      # physical cycle finished; awaiting rule evaluation
    VERIFIED = "VERIFIED"        # terminal: all verification rules passed
    UNVERIFIED = "UNVERIFIED"    # terminal: cycle finished but a rule failed
    REJECTED = "REJECTED"        # terminal: stopped before extraction, nothing deposited
    FAULTED = "FAULTED"          # terminal: fault after extraction, before completion


TERMINAL_STATES = frozenset(
    {EventState.VERIFIED, EventState.UNVERIFIED, EventState.REJECTED, EventState.FAULTED}
)


class CycleStage(str, Enum):
    """Physical station stages, in required order (reported by Team 2)."""

    DETECTED = "DETECTED"
    IDENTIFIED = "IDENTIFIED"
    POSITION_VERIFIED = "POSITION_VERIFIED"
    LIQUID_ACCEPTED = "LIQUID_ACCEPTED"
    EXTRACTED = "EXTRACTED"
    VOLUME_VALIDATED = "VOLUME_VALIDATED"
    SANITIZED = "SANITIZED"
    RETRACTED = "RETRACTED"
    COMPLETED = "COMPLETED"


# Canonical order; index = position in the sequence.
STAGE_ORDER: tuple[CycleStage, ...] = tuple(CycleStage)


class ReasonCode(str, Enum):
    """Why an event was withheld from VERIFIED status.

    Each code maps to exactly one terminal state (see docs/STATE_MODEL.md).
    """

    # -> REJECTED (no deposit occurred)
    IDENTITY_FAILURE = "IDENTITY_FAILURE"              # RFID / receptacle id unreadable or missing
    ACCOUNT_MISSING = "ACCOUNT_MISSING"                # no authorized account associated
    ABORTED_PRE_EXTRACTION = "ABORTED_PRE_EXTRACTION"  # cycle ended before EXTRACTED
    LIQUID_NOT_ACCEPTED = "LIQUID_NOT_ACCEPTED"        # liquid-condition check failed

    # -> FAULTED (deposit occurred, cycle did not finish)
    POST_EXTRACTION_FAULT = "POST_EXTRACTION_FAULT"

    # -> UNVERIFIED (cycle finished, but cannot be vouched for)
    VOLUME_MISSING = "VOLUME_MISSING"
    VOLUME_MISMATCH = "VOLUME_MISMATCH"                # measurements disagree beyond tolerance
    VOLUME_LOW_CONFIDENCE = "VOLUME_LOW_CONFIDENCE"
    SANITATION_INCOMPLETE = "SANITATION_INCOMPLETE"
    MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
    STAGE_SEQUENCE_INVALID = "STAGE_SEQUENCE_INVALID"  # stages out of order / skipped
    TIMESTAMP_ORDER_INVALID = "TIMESTAMP_ORDER_INVALID"  # time goes backwards
