"""Changing the compliance rules (CFG-06). Only an admin (the customer's) does; a change is a new
version taking effect from a day that has not started, so what applied on a past day never changes.
The audit event is the LAST write of the transaction."""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.utils import timezone
from wfm_engine.compliance import Rules, floor_warnings, invalid_reason

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError

from .models import ComplianceRuleVersion


def _label(rules: Rules | None) -> str | None:
    if rules is None:
        return None
    cap = rules.max_weekly_hours if rules.max_weekly_hours is not None else "none"
    return (
        f"rest {rules.min_rest_hours} h, {rules.max_consecutive_days} days in a row, "
        f"weekly cap {cap}"
    )


def set_rules(
    *, user: User, effective_from: date, rules: Rules
) -> tuple[ComplianceRuleVersion, list[str]]:
    """Add (or, for a day not yet started, replace) the version taking effect on `effective_from`.
    Returns it with the warnings for rules looser than the statutory floor (never a refusal)."""
    why = invalid_reason(rules)
    if why is not None:
        raise ApiError(422, "rules.invalid", "Rule refused", why)
    if effective_from < timezone.localdate():
        raise ApiError(
            422, "rules.in_the_past", "Rule refused", "Rules can only start today or later."
        )
    with transaction.atomic():
        existing = (
            ComplianceRuleVersion.objects.select_for_update(no_key=True)
            .filter(effective_from=effective_from)
            .first()
        )
        before = (
            Rules(existing.min_rest_hours, existing.max_consecutive_days, existing.max_weekly_hours)
            if existing
            else None
        )
        version, _ = ComplianceRuleVersion.objects.update_or_create(
            effective_from=effective_from,
            defaults={
                "min_rest_hours": rules.min_rest_hours,
                "max_consecutive_days": rules.max_consecutive_days,
                "max_weekly_hours": rules.max_weekly_hours,
                "created_by": user,
            },
        )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.COMPLIANCE_RULES_CHANGED,
            entity_type="compliance_rules",
            entity_id=str(effective_from),
            changes=[
                audit.FieldChange(
                    "compliance_rules", str(effective_from), "rules", _label(before), _label(rules)
                )
            ],
        )
    return version, floor_warnings(rules)
