"""Event persistence.                                                OWNER: Teammate C

Contract:
    store.get(event_id)   -> DisposalEvent | None
    store.insert(event)   -> None, raises DuplicateEventError if event_id exists

InMemoryEventStore is complete and is what tests use. SQLiteEventStore is the
real implementation for the API.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .errors import DuplicateEventError
from .models import DisposalEvent


class EventStore(ABC):
    @abstractmethod
    def get(self, event_id: str) -> Optional[DisposalEvent]: ...

    @abstractmethod
    def insert(self, event: DisposalEvent) -> None:
        """Store a NEW event. Must raise DuplicateEventError if event_id exists.
        Events are never updated or deleted (terminal states are immutable)."""


class InMemoryEventStore(EventStore):
    """Dictionary-backed store for tests. Complete; do not change behavior."""

    def __init__(self):
        self._events: dict[str, DisposalEvent] = {}

    def get(self, event_id: str) -> Optional[DisposalEvent]:
        return self._events.get(event_id)

    def insert(self, event: DisposalEvent) -> None:
        if event.event_id in self._events:
            raise DuplicateEventError(event.event_id)
        self._events[event.event_id] = event


class SQLiteEventStore(EventStore):
    """SQLite-backed store.

    Suggested table:
        CREATE TABLE IF NOT EXISTS events (
            event_id            TEXT PRIMARY KEY,   -- the UNIQUE constraint IS the duplicate guard
            station_id          TEXT NOT NULL,
            cycle_id            TEXT NOT NULL,
            state               TEXT NOT NULL,
            source_payload_hash TEXT NOT NULL,
            created_at          TEXT NOT NULL,
            payload_json        TEXT NOT NULL       -- event.model_dump_json()
        );
    Turn sqlite3.IntegrityError on insert into DuplicateEventError.
    Rebuild events with DisposalEvent.model_validate_json(payload_json).
    """

    def __init__(self, path: str = "vde_events.db"):
        self.path = path
        raise NotImplementedError("Teammate C")

    def get(self, event_id: str) -> Optional[DisposalEvent]:
        raise NotImplementedError("Teammate C")

    def insert(self, event: DisposalEvent) -> None:
        raise NotImplementedError("Teammate C")
