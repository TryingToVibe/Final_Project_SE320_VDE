"""Event identifier derivation.

The Event ID is *derived* from the cycle, never randomly generated, so a
retried or duplicated submission for the same cycle always maps to the same
event. This is the basis of duplicate-safe creation.

NOTE: today we assume Team 2 supplies a unique `cycle_id` per station. If that
assumption changes, this is the ONLY function that needs to change.
"""
import uuid

# Fixed namespace for this component. Never change it: doing so would change
# every Event ID ever issued.
VDE_NAMESPACE = uuid.UUID("6f1c2a52-6a0e-4c1b-9a43-3c7d0e2f9b10")


def derive_event_id(station_id: str, cycle_id: str) -> str:
    """Deterministic, collision-resistant Event ID for one station cycle."""
    if not station_id or not cycle_id:
        raise ValueError("station_id and cycle_id are both required to derive an event id")
    return str(uuid.uuid5(VDE_NAMESPACE, f"{station_id}:{cycle_id}"))
