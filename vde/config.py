"""Tunable verification thresholds.

PLACEHOLDER VALUES. These are open questions 1 and 2 in STATE_MODEL.md and
must be confirmed with Team 1 before final submission. Keep every threshold
here (never hard-code numbers inside rules.py) so a change is one edit.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationConfig:
    # R8: primary_ml and secondary_ml must agree within BOTH limits below.
    volume_tolerance_ml: float = 5.0        # placeholder: absolute difference, mL
    volume_tolerance_pct: float = 2.0       # placeholder: relative difference, % of validated_ml
    min_volume_confidence: float = 0.90     # placeholder: Team 1 confidence, 0..1


DEFAULT_CONFIG = VerificationConfig()
