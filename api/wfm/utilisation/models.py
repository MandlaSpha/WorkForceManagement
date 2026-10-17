"""Commercial terms of a contract that utilisation and cost are held against (UTL-01, UTL-02).

The target is a percentage of worked time that should be billable. The monthly revenue is a
commercial figure: it is read back only by the roles that may see pay and cost, and it never
appears in the audit trail, logs or traces.
"""

from __future__ import annotations

from typing import Any, Self

from django.db import models

from wfm.accounts.models import User
from wfm.core.scoping import ScopedQuerySet

from .policy import GROUP_ROLES


class TermsQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in GROUP_ROLES else self.none()


class ContractTerms(models.Model):
    contract = models.OneToOneField(
        "contracts.Contract", on_delete=models.CASCADE, related_name="terms"
    )
    utilisation_target_pct = models.DecimalField(max_digits=5, decimal_places=2)
    monthly_revenue_zar = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = TermsQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(utilisation_target_pct__gt=0)
                & models.Q(utilisation_target_pct__lte=100),
                name="utilisation_target_range",
            ),
            models.CheckConstraint(
                condition=models.Q(monthly_revenue_zar__isnull=True)
                | models.Q(monthly_revenue_zar__gte=0),
                name="utilisation_revenue_not_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"terms of contract {self.contract_id}"
