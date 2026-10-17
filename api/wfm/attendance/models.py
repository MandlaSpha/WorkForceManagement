"""Imported agent-state intervals: what the ACD says each person was doing (ATT-01).

The state feed format is SYNTHETIC until the ACD vendor confirms the real one (tech spec 4.19).
A row is one interval of one state for one mapped person. It is attendance data about a named
person, so who may read it is decided here, in `for_user`, and nowhere else. Pay is never involved.
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


class StateQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        if user.role in IMPORT_ROLES:
            return self
        if user.role in TEAM_ROLES:  # a lead: their own team (and themselves)
            return self.filter(
                models.Q(employee__manager__user=user) | models.Q(employee__user=user)
            )
        if user.role == Role.AGENT:
            return self.filter(employee__user=user)  # only their own day, never a colleague's
        return self.none()


class AgentStateImport(models.Model):
    """One uploaded file: counts only. The file itself and the logins in it are not kept here."""

    file_name = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    rows_read = models.PositiveIntegerField()
    rows_inserted = models.PositiveIntegerField()
    rows_duplicate = models.PositiveIntegerField()
    rows_rejected = models.PositiveIntegerField()
    rows_unmapped = models.PositiveIntegerField()
    created_at = models.DateTimeField(
        db_default=models.Func(function="now", output_field=models.DateTimeField())
    )

    objects = ImportQuerySet.as_manager()

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"state import {self.pk}"


class AgentStateInterval(models.Model):
    """`employee` is set from the `AgentLogin` table when the file is imported; a login that is
    not mapped is reported and never stored. One interval per login and start time."""

    batch = models.ForeignKey(AgentStateImport, on_delete=models.CASCADE, related_name="+")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="+")
    login = models.CharField(max_length=100)
    state = models.CharField(max_length=12)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    objects = StateQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["login", "start_at"], name="attendance_state_unique"),
            models.CheckConstraint(
                condition=models.Q(end_at__gt=models.F("start_at")), name="attendance_state_order"
            ),
        ]
        indexes = [models.Index(fields=["employee", "start_at"], name="attendance_state_person")]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.state} {self.start_at:%Y-%m-%d %H:%M}"
