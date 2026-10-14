"""Agents needed for a half-hour of calls (requirements ENG-01, ENG-02). One place, so a forecast
and a what-if scenario can never disagree about how a requirement is worked out."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from wfm_engine.erlang import required_agents
from wfm_engine.kpi import INTERVAL_MINUTES

from wfm.telephony.models import Queue

INTERVAL_S = INTERVAL_MINUTES * 60


@dataclass(frozen=True, slots=True)
class Assumptions:
    sl_target_pct: float  # e.g. 80: answer 80% of calls ...
    sl_threshold_s: int  # ... within 20 seconds
    occupancy_ceiling_pct: float
    shrinkage_pct: float

    @classmethod
    def of_queue(cls, queue: Queue) -> Assumptions:
        return cls(
            float(queue.sl_target_pct),
            queue.sl_threshold_s,
            float(queue.occupancy_ceiling_pct),
            float(queue.shrinkage_pct),
        )

    @classmethod
    def of_params(cls, params: dict[str, Any], fallback: Assumptions) -> Assumptions:
        """The assumptions a forecast version was run with; a version without them (it should not
        happen) falls back to the queue's current ones."""
        try:
            return cls(
                float(params["slTargetPct"]),
                int(params["slThresholdS"]),
                float(params["occupancyCeilingPct"]),
                float(params["shrinkagePct"]),
            )
        except (KeyError, TypeError, ValueError):
            return fallback

    def changed(
        self, sl_target_pct: float | None = None, shrinkage_pct: float | None = None
    ) -> Assumptions:
        return replace(
            self,
            sl_target_pct=self.sl_target_pct if sl_target_pct is None else sl_target_pct,
            shrinkage_pct=self.shrinkage_pct if shrinkage_pct is None else shrinkage_pct,
        )


def requirement(
    volume: float, aht_s: float | None, assumptions: Assumptions
) -> tuple[int | None, int | None]:
    """Agents on the phone, and agents to roster once shrinkage is added. No call volume needs
    nobody; calls with no known handling time cannot be staffed honestly (None)."""
    if volume <= 0:
        return 0, 0
    if aht_s is None or aht_s <= 0:
        return None, None
    common: dict[str, Any] = {
        "volume": volume,
        "interval_s": INTERVAL_S,
        "aht_s": aht_s,
        "sl_target": assumptions.sl_target_pct / 100,
        "threshold_s": assumptions.sl_threshold_s,
        "occupancy_ceiling": assumptions.occupancy_ceiling_pct / 100,
    }
    try:
        raw = required_agents(**common, shrinkage=0.0)
        with_shrinkage = required_agents(**common, shrinkage=assumptions.shrinkage_pct / 100)
    except ValueError:
        return None, None
    return raw, with_shrinkage
