"""The latest hiring plan, as a read-only summary for the investment-board pack (RPT-09).

Headcount only: the cost per person is pay data and is never returned here, whatever the role.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from wfm_engine import hiring

from wfm.accounts.models import User

from .models import HiringPlan


@dataclass(frozen=True, slots=True)
class PlanMonth:
    month: date
    required: float
    headcount: float
    hires: int
    effective: float
    gap: float


@dataclass(frozen=True, slots=True)
class PlanSummary:
    name: str
    months: list[PlanMonth]


def latest_plan(user: User) -> PlanSummary | None:
    """The newest hiring plan the user may read, or None (no plan, or a role that may not read
    plans: the two are deliberately indistinguishable)."""
    plan = HiringPlan.objects.for_user(user).order_by("-created_at", "-id").first()
    if plan is None:
        return None
    rows = hiring.plan(
        plan.required, float(plan.incumbents), float(plan.attrition_pct) / 100, plan.ramp
    )
    first = plan.start_month.year * 12 + plan.start_month.month - 1
    return PlanSummary(
        name=plan.name,
        months=[
            PlanMonth(
                month=date((first + r.index) // 12, (first + r.index) % 12 + 1, 1),
                required=r.required,
                headcount=round(r.headcount, 1),
                hires=r.hires,
                effective=round(r.effective, 1),
                gap=round(r.gap, 1),
            )
            for r in rows
        ],
    )
