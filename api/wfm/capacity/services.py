"""Setting the workforce limits. The write and its audit event share one transaction, the audit
event as the LAST write (hard rule: the audit insert holds the audit-chain lock until commit)."""

from __future__ import annotations

from django.db import transaction

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError

from .models import CapacityLimits

MAX_POOL = 5000


def set_limits(*, user: User, permanent_limit: int, seasonal_limit: int) -> CapacityLimits:
    """Set the permanent and seasonal pools and mark them confirmed."""
    for name, value in (("permanent", permanent_limit), ("seasonal", seasonal_limit)):
        if not 0 <= value <= MAX_POOL:
            raise ApiError(
                422,
                f"capacity.{name}_invalid",
                "Invalid request",
                f"The {name} pool is between 0 and {MAX_POOL} people.",
            )
    if permanent_limit + seasonal_limit == 0:
        raise ApiError(
            422, "capacity.no_workforce", "Invalid request", "The workforce cannot be empty."
        )

    with transaction.atomic():
        limits: CapacityLimits
        limits, _ = CapacityLimits.objects.select_for_update().get_or_create(pk=1)
        wanted = {"permanent_limit": permanent_limit, "seasonal_limit": seasonal_limit}
        changes = [
            audit.FieldChange("capacity_limits", "1", name, str(getattr(limits, name)), str(value))
            for name, value in wanted.items()
            if getattr(limits, name) != value
        ]
        if not limits.confirmed:
            changes.append(audit.FieldChange("capacity_limits", "1", "confirmed", "False", "True"))
        limits.permanent_limit = permanent_limit
        limits.seasonal_limit = seasonal_limit
        limits.confirmed = True
        limits.updated_by = user
        limits.save()
        if changes:
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.CAPACITY_LIMITS_CHANGED,
                entity_type="capacity_limits",
                entity_id="1",
                changes=changes,
            )
    return limits
