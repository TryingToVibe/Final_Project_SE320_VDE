"""Exceptions shared across the VDE package.

Each maps to one API error code (see vde/api.py) so every team sees the same
`{"error": {"code": ...}}` value for the same problem.
"""


class VDEError(Exception):
    """Base class. `code` is the stable UPPER_SNAKE_CASE API error code."""

    code = "VDE_ERROR"


class DuplicateEventError(VDEError):
    """Raised by EventStore.insert() when the event_id already exists."""

    code = "DUPLICATE_EVENT"

    def __init__(self, event_id: str):
        self.event_id = event_id
        super().__init__(f"Event {event_id} already exists")


class EventConflictError(VDEError):
    """Same station + cycle submitted again with a DIFFERENT payload (HTTP 409)."""

    code = "EVENT_CONFLICT"

    def __init__(self, event_id: str, stored_hash: str, new_hash: str):
        self.event_id = event_id
        self.stored_hash = stored_hash
        self.new_hash = new_hash
        super().__init__(f"Event {event_id} already exists with a different payload")


class EventNotFoundError(VDEError):
    """Lookup for an event_id that does not exist (HTTP 404)."""

    code = "EVENT_NOT_FOUND"

    def __init__(self, event_id: str):
        self.event_id = event_id
        super().__init__(f"Event {event_id} not found")
