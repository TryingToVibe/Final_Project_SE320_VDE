"""Duplicate-safe event creation.                                    OWNER: Teammate C

Contract:
    submit_report(report, store, now, evaluator=evaluate) -> (event, created)

`evaluator` is injectable so this can be built and tested BEFORE the real rules
engine is finished: pass vde.testing.fake_evaluate in your tests.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from .errors import DuplicateEventError, EventConflictError
from .identity import derive_event_id, payload_hash
from .models import CycleReport, DisposalEvent
from .rules import evaluate
from .store import EventStore

Evaluator = Callable[[CycleReport, datetime], DisposalEvent]


def submit_report(
    report: CycleReport,
    store: EventStore,
    now: datetime,
    evaluator: Evaluator | None = None,
) -> tuple[DisposalEvent, bool]:
    """Turn a report into a stored event, exactly once per station cycle.

    Algorithm:
      1. event_id = identity.derive_event_id(report.station_id, report.cycle_id)
         new_hash = identity.payload_hash(report)
      2. existing = store.get(event_id)
         - exists and existing.source_payload_hash == new_hash -> return (existing, False)   # HTTP 200
         - exists and hashes differ -> raise EventConflictError                             # HTTP 409
      3. event = evaluator(report, now)      (default: rules.evaluate)
      4. store.insert(event); if DuplicateEventError (two requests raced), re-run step 2
      5. return (event, True)                                                                # HTTP 201
    """
    event_id = derive_event_id(report.station_id, report.cycle_id)
    new_hash = payload_hash(report)

    existing = store.get(event_id)
    if existing is not None:
        if existing.source_payload_hash == new_hash:
            return existing, False
        raise EventConflictError(event_id, existing.source_payload_hash, new_hash)

    if evaluator is None:
        evaluator = evaluate

    event = evaluator(report, now)

    try:
        store.insert(event)
    except DuplicateEventError:
        existing = store.get(event_id)
        if existing is None:
            raise
        if existing.source_payload_hash == new_hash:
            return existing, False
        raise EventConflictError(event_id, existing.source_payload_hash, new_hash)

    return event, True
