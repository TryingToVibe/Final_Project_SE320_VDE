"""Event persistence.                                                OWNER: Teammate C

Contract:
    store.get(event_id)   -> DisposalEvent | None
    store.insert(event)   -> None, raises DuplicateEventError if event_id exists

InMemoryEventStore is complete and is what tests use. SQLiteEventStore is the
real implementation for the API.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
import sqlite3
from typing import Iterator, Optional

from .errors import DuplicateEventError
from .models import DisposalEvent, to_utc_iso


class EventStore(ABC):
    @abstractmethod
    def get(self, event_id: str) -> Optional[DisposalEvent]:
        ...

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
    """SQLite-backed store. The PRIMARY KEY on event_id is the duplicate guard.

    Events are stored as event.model_dump_json() and rebuilt with
    DisposalEvent.model_validate_json(). Timestamps are serialized to
    milliseconds, so a stored event can differ from the in-memory one by
    sub-millisecond precision.
    """

    def __init__(self, path: str = "vde_events.db"):
        self.path = path

        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    station_id TEXT NOT NULL,
                    cycle_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    source_payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # `with sqlite3.connect(...)` only commits or rolls back; it does NOT
        # close the connection. An open connection keeps the .db file locked on
        # Windows, so close it explicitly.
        connection = sqlite3.connect(self.path)
        try:
            with connection:  # commit on success, roll back on error
                yield connection
        finally:
            connection.close()

    def get(self, event_id: str) -> Optional[DisposalEvent]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()

        if row is None:
            return None

        return DisposalEvent.model_validate_json(row[0])

    def insert(self, event: DisposalEvent) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO events (
                        event_id, station_id, cycle_id, state,
                        source_payload_hash, created_at, payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.station_id,
                        event.cycle_id,
                        event.state.value,
                        event.source_payload_hash,
                        to_utc_iso(event.created_at),
                        event.model_dump_json(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateEventError(event.event_id) from exc
