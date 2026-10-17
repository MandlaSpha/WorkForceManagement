"""Quality results imported from the quality tool (QUA-01).

The scoring stays in the quality tool: a row here is a score that was already given to one mapped
person. It is information about a named person, so who may read it is decided here, in `for_user`,
and nowhere else: planners and admins, the lead of the person's team, and the person. Nobody else,
and no view ranks or compares people.
"""

from __future__ import annotations

from typing import Any, Self

from django.db import models

from wfm.accounts.models import Role, User
from wfm.core.scoping import ScopedQuerySet
from wfm.scheduling.models import Employee

from .policy import IMPORT_ROLES, TEAM_ROLES


class ImportQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in IMPORT_ROLES else self.none()


class ResultQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        if user.role in IMPORT_ROLES:
            return self
        if user.role in TEAM_ROLES:  # a lead: their own team (and themselves)
            return self.filter(
                models.Q(employee__manager__user=user) | models.Q(employee__user=user)
            )
        if user.role == Role.AGENT:
            return self.filter(employee__user=user)  # only their own, never a colleague's
        return self.none()


class QualityImport(models.Model):
    """One uploaded file: counts only. The file and the logins in it are not kept here."""

    file_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    rows_read = models.PositiveIntegerField()
    rows_created = models.PositiveIntegerField()
    rows_updated = models.PositiveIntegerField()
    rows_unchanged = models.PositiveIntegerField()
    rows_rejected = models.PositiveIntegerField()
    rows_unmapped = models.PositiveIntegerField()
    created_at = models.DateTimeField(
        db_default=models.Func(function="now", output_field=models.DateTimeField())
    )

    objects = ImportQuerySet.as_manager()

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"quality import {self.pk}"


class QualityResult(models.Model):
    """One evaluation of one person: a call or a ticket. A later file may correct it (same person,
    day, kind and reference), so the quality tool stays the source of truth."""

    batch = models.ForeignKey(QualityImport, on_delete=models.SET_NULL, null=True, related_name="+")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="+")
    evaluated_on = models.DateField()
    kind = models.CharField(max_length=6)  # call or ticket
    ref = models.CharField(max_length=40, blank=True)  # the quality tool's evaluation id
    score_pct = models.DecimalField(max_digits=5, decimal_places=2)
    csat = models.PositiveSmallIntegerField(null=True, blank=True)  # 1 to 5
    coaching_due = models.DateField(null=True, blank=True)

    objects = ResultQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "evaluated_on", "kind", "ref"], name="quality_result_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(score_pct__gte=0, score_pct__lte=100),
                name="quality_score_range",
            ),
            models.CheckConstraint(
                condition=models.Q(csat__isnull=True) | models.Q(csat__gte=1, csat__lte=5),
                name="quality_csat_range",
            ),
        ]
        indexes = [models.Index(fields=["employee", "evaluated_on"], name="quality_by_person")]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.kind} {self.evaluated_on}"
