"""Event identifier derivation.

The Event ID is *derived* from the cycle, never randomly generated, so a
retried or duplicated submission for the same cycle always maps to the same
event. This is the basis of duplicate-safe creation.

NOTE: today we assume Team 2 supplies a unique `cycle_id` per station. If that
assumption changes, this is the ONLY function that needs to change.
"""
import hashlib
import json
import uuid

# Fixed namespace for this component. Never change it: doing so would change
# every Event ID ever issued.
VDE_NAMESPACE = uuid.UUID("6f1c2a52-6a0e-4c1b-9a43-3c7d0e2f9b10")


def derive_event_id(station_id: str, cycle_id: str) -> str:
    """Deterministic, collision-resistant Event ID for one station cycle."""
    if not station_id or not cycle_id:
        raise ValueError("station_id and cycle_id are both required to derive an event id")
    return str(uuid.uuid5(VDE_NAMESPACE, f"{station_id}:{cycle_id}"))


def payload_hash(report) -> str:
    """SHA-256 of the canonical CycleReport JSON (sorted keys, UTC timestamps).

    Two reports for the same cycle with equal hashes are the same submission;
    different hashes mean a conflicting resubmission.

    `reported_at` is excluded: it records when the report was sent, not what
    happened in the cycle, so a station retry must still hash the same.
    """
    data = report.model_dump(mode="json", exclude={"reported_at"})
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
