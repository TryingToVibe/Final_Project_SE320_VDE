"""Event state machine: which state changes are legal.

This module only answers "is this transition allowed?". *Which* transition to
take is decided by the rules engine (step 2). Keeping them apart means the
state model can be documented and tested on its own.
"""
from .enums import EventState, TERMINAL_STATES

S = EventState

ALLOWED_TRANSITIONS: dict[EventState, frozenset[EventState]] = {
    S.ATTEMPTED: frozenset({S.IN_PROGRESS, S.REJECTED}),
    S.IN_PROGRESS: frozenset({S.COMPLETED, S.REJECTED, S.FAULTED}),
    S.COMPLETED: frozenset({S.VERIFIED, S.UNVERIFIED}),
    # Terminal states never change: that is what makes an event "trusted".
    S.VERIFIED: frozenset(),
    S.UNVERIFIED: frozenset(),
    S.REJECTED: frozenset(),
    S.FAULTED: frozenset(),
}


class InvalidTransitionError(Exception):
    def __init__(self, current: EventState, target: EventState):
        self.current = current
        self.target = target
        super().__init__(f"Illegal event state transition {current.value} -> {target.value}")


def can_transition(current: EventState, target: EventState) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def transition(current: EventState, target: EventState) -> EventState:
    """Return `target` if the move is legal, otherwise raise."""
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
    return target


def is_terminal(state: EventState) -> bool:
    return state in TERMINAL_STATES
