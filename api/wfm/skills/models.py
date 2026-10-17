"""Credentials on the employee and the credentials a queue requires (SKL-01, WEL-02).

A credential (certification, language, security clearance) is information about a named person, so
who reads it is decided in `for_user` and nowhere else. The queues a person can work, with a
level, already live in `scheduling.EmployeeSkill`; this adds the rest.
"""

from __future__ import annotations

from typing import Any, Self

from django.db import models

from wfm.accounts.models import Role, User
from wfm.core.scoping import ScopedQuerySet
from wfm.scheduling.models import Employee
from wfm.telephony.models import Queue

from .policy import ALL_SCOPE_ROLES, REQUIREMENT_READ_ROLES, TEAM_ROLES


class CredentialKind(models.TextChoices):
    CERTIFICATION = "certification", "Certification"
    LANGUAGE = "language", "Language"
    CLEARANCE = "clearance", "Security clearance"


class CredentialQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        if user.role in ALL_SCOPE_ROLES:
            return self
        if user.role in TEAM_ROLES:  # a lead: their own team (and themselves)
            return self.filter(
                models.Q(employee__manager__user=user) | models.Q(employee__user=user)
            )
        if user.role == Role.AGENT:
            return self.filter(employee__user=user)
        return self.none()


class EmployeeCredential(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="credentials")
    kind = models.CharField(max_length=15, choices=CredentialKind.choices)
    name = models.CharField(max_length=80)
    expires_on = models.DateField(null=True, blank=True)  # held until the end of this day
    updated_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")

    objects = CredentialQuerySet.as_manager()

    class Meta:
        ordering = ["kind", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "kind", "name"], name="skills_credential_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.kind} {self.name}"


class RequirementQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self if user.role in REQUIREMENT_READ_ROLES else self.none()


class QueueRequirement(models.Model):
    """At least `min_people` people holding this credential on every shift rostered on the queue."""

    queue = models.ForeignKey(Queue, on_delete=models.PROTECT, related_name="requirements")
    kind = models.CharField(max_length=15, choices=CredentialKind.choices)
    name = models.CharField(max_length=80)
    min_people = models.PositiveSmallIntegerField(default=1)

    objects = RequirementQuerySet.as_manager()

    class Meta:
        ordering = ["queue_id", "kind", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["queue", "kind", "name"], name="skills_requirement_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(min_people__gte=1), name="skills_requirement_min_people"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.queue_id} {self.kind} {self.name} x{self.min_people}"
