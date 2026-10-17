"""Named backup teams per queue (BCP-01): the people who could be asked to cover that queue when
a site fails or an outbreak removes staff. A team is a list, not a roster: nobody is moved by
being on it."""

from __future__ import annotations

from typing import Any, Self

from django.db import models

from wfm.accounts.models import User
from wfm.core.scoping import ScopedQuerySet
from wfm.scheduling.models import Employee
from wfm.telephony.models import Queue

from .policy import READ_ROLES


class ContinuityQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in READ_ROLES else self.none()


class BackupTeam(models.Model):
    queue = models.ForeignKey(Queue, on_delete=models.PROTECT, related_name="backup_teams")
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(
        db_default=models.Func(function="now", output_field=models.DateTimeField())
    )

    objects = ContinuityQuerySet.as_manager()

    class Meta:
        ordering = ["queue_id", "name"]
        constraints = [
            models.UniqueConstraint(fields=["queue", "name"], name="continuity_team_unique")
        ]

    def __str__(self) -> str:
        return f"{self.queue_id} {self.name}"


class BackupMember(models.Model):
    team = models.ForeignKey(BackupTeam, on_delete=models.CASCADE, related_name="members")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="+")
    added_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")

    objects = ContinuityQuerySet.as_manager()

    class Meta:
        ordering = ["employee__emp_no"]
        constraints = [
            models.UniqueConstraint(fields=["team", "employee"], name="continuity_member_unique")
        ]

    def __str__(self) -> str:
        return f"{self.team_id} {self.employee_id}"
