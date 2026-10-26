"""Test helpers shared by everyone. Not used in production.

fake_evaluate lets Teammates B and C test their code before the real rules
engine (vde/rules.py) is finished. It only checks the account, so it is NOT a
substitute for the real rules.
"""
from __future__ import annotations

from datetime import datetime

from .enums import EventState, ReasonCode
from .identity import derive_event_id, payload_hash
from .models import CycleReport, DisposalEvent, RuleResult


def fake_evaluate(report: CycleReport, now: datetime) -> DisposalEvent:
    """VERIFIED if account + receptacle + validated volume exist, else REJECTED."""
    ok = bool(report.account_id and report.receptacle_id and report.volume
              and report.volume.validated_ml is not None)
    return DisposalEvent(
        event_id=derive_event_id(report.station_id, report.cycle_id),
        state=EventState.VERIFIED if ok else EventState.REJECTED,
        reasons=[] if ok else [ReasonCode.ACCOUNT_MISSING],
        rule_results=[RuleResult(rule_id="FAKE", passed=ok,
                                 reason=None if ok else ReasonCode.ACCOUNT_MISSING)],
        station_id=report.station_id,
        cycle_id=report.cycle_id,
        receptacle_id=report.receptacle_id,
        account_id=report.account_id,
        deposit_volume_ml=report.volume.validated_ml if ok else None,
        sanitation_fluid_ml=report.sanitation.fluid_ml if report.sanitation else None,
        created_at=now,
        source_payload_hash=payload_hash(report),
    )
