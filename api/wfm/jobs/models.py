"""Background jobs: slow work (a forecast, an auto-schedule) that the worker does while the
screen asks how it is getting on.

A job belongs to the person who started it and to nobody else. It holds no personal data: its
parameters are ids and dates, its result is counts and ids, and a failure is a code and a sentence.
What the work changed is in the audit trail, recorded by the same services a click would use.
"""

from __future__ import annotations

import uuid
from typing import Any, Self

from django.db import models

from wfm.accounts.models import User
from wfm.core.scoping import ScopedQuerySet


class JobStatus(models.TextChoices):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


ACTIVE = (JobStatus.QUEUED, JobStatus.RUNNING)


class JobQuerySet(ScopedQuerySet):
    def for_user(self, user: Any) -> Self:
        return self.filter(owner=user)  # nobody sees another person's jobs, whatever their role


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=40)
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=10, choices=JobStatus.choices, default=JobStatus.QUEUED)
    params = models.JSONField(default=dict)
    result = models.JSONField(null=True, blank=True)
    error_code = models.CharField(max_length=60, blank=True)
    error_detail = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    objects = JobQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=["owner", "kind", "status"], name="jobs_owner_kind_status")]

    def __str__(self) -> str:
        return f"{self.kind} {self.status}"
