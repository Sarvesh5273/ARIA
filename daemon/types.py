"""Shared contract types used by both Soul Filter (Module 5) and
Needs System (Module 2). Lives here so neither module is the
consumer of the other's definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NeedState(Enum):
    """Categorical psychological-need state (Addendum §3: the four needs are
    categorical, never continuously draining)."""
    SATISFIED = "satisfied"
    DUE = "due"
    NEGLECTED = "neglected"


@dataclass(frozen=True)
class NeedStates:
    """The four categorical needs + Energy (continuous substrate).
    Soul_Filter reads energy ONLY through the <30 / <20 operational
    threshold gates (Addendum §3). The four categorical needs influence
    fields indirectly via the AppraisalResult they shaped upstream."""
    connection: NeedState = NeedState.SATISFIED
    growth: NeedState = NeedState.SATISFIED
    purpose: NeedState = NeedState.SATISFIED
    continuity: NeedState = NeedState.SATISFIED
    energy: float = 100.0


# Energy operational threshold gates (Addendum §3; v4 soul_filter table).
# These are IN-SPEC operational thresholds, NOT invented numbers.
ENERGY_LOW = 30.0        # v4 "Energy low (below 30)"
ENERGY_CRITICAL = 20.0   # v4 "Energy critically low (below 20)"