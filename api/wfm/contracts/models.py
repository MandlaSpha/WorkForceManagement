"""Customers and the contracts that hold queues to a service level (ENG-05, CFG-01, CAP-04).

A contract groups queues and carries the service-level target and threshold the customer is
promised. Saving a contract writes those two figures onto each of its queues, so the staffing
maths (which reads the queue) needs no change. Occupancy and shrinkage stay operational settings
of the queue.
"""

from __future__ import annotations

from typing import Any, Self

from django.db import models

from wfm.core.scoping import ScopedQuerySet

from .policy import READ_ROLES


class ReadScopedQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in READ_ROLES else self.none()


class Customer(models.Model):
    name = models.CharField(max_length=100, unique=True)

    objects = ReadScopedQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Contract(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="contracts")
    name = models.CharField(max_length=100)
    sl_target_pct = models.DecimalField(max_digits=5, decimal_places=2, default=80)
    sl_threshold_s = models.PositiveSmallIntegerField(default=20)
    active = models.BooleanField(default=True)

    objects = ReadScopedQuerySet.as_manager()

    class Meta:
        ordering = ["customer__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["customer", "name"], name="contracts_unique_name"),
            models.CheckConstraint(
                condition=models.Q(sl_target_pct__gt=0) & models.Q(sl_target_pct__lte=100),
                name="contracts_sl_target_range",
            ),
            models.CheckConstraint(
                condition=models.Q(sl_threshold_s__gte=1) & models.Q(sl_threshold_s__lte=600),
                name="contracts_sl_threshold_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.customer_id} {self.name}"


class ContractQueue(models.Model):
    """A queue belongs to at most one contract."""

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="members")
    queue = models.OneToOneField(
        "telephony.Queue", on_delete=models.CASCADE, related_name="contract_link"
    )

    objects = ReadScopedQuerySet.as_manager()

    def __str__(self) -> str:
        return f"{self.contract_id} {self.queue_id}"
