"""Append-only audit trail (requirements AUD-01..AUD-14, tech spec section 6.1).

`actor_user_id` is a plain integer rather than a foreign key on purpose: deleting or
anonymising a user must never cascade into, or be blocked by, the audit trail.
"""

from __future__ import annotations

from django.db import models


class Outcome(models.TextChoices):
    SUCCESS = "success", "Success"
    DENIED = "denied", "Denied"
    FAILED = "failed", "Failed"


class ActorType(models.TextChoices):
    USER = "user", "User"
    SYSTEM = "system", "System job"
    INTEGRATION = "integration", "Integration"


class Action(models.TextChoices):
    LOGIN_SUCCESS = "auth.login", "Login"
    LOGIN_FAILED = "auth.login_failed", "Login failed"
    LOGIN_LOCKED = "auth.login_locked", "Login refused: account locked"
    LOGOUT = "auth.logout", "Logout"
    ACCESS_DENIED = "access.denied", "Access denied"


class AuditEvent(models.Model):
    # The database clock sets this, never the client (AUD-02).
    occurred_at = models.DateTimeField(
        db_default=models.Func(function="clock_timestamp", output_field=models.DateTimeField()),
        editable=False,
        db_index=True,
    )
    actor_user_id = models.BigIntegerField(null=True, db_index=True)
    actor_role = models.CharField(max_length=20, blank=True)
    actor_type = models.CharField(max_length=12, choices=ActorType.choices)
    subject_employee_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    action = models.CharField(max_length=60, db_index=True)
    entity_type = models.CharField(max_length=60, blank=True)
    entity_id = models.CharField(max_length=200, blank=True)
    outcome = models.CharField(max_length=8, choices=Outcome.choices)
    reason = models.CharField(max_length=300, blank=True)
    request_id = models.CharField(max_length=40, blank=True)
    trace_id = models.CharField(max_length=40, blank=True)
    session_hash = models.CharField(max_length=40, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    batch_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["entity_type", "entity_id"], name="audit_entity_idx")]

    def __str__(self) -> str:
        return f"{self.occurred_at:%Y-%m-%d %H:%M:%S} {self.action} {self.outcome}"


class AuditChange(models.Model):
    event = models.ForeignKey(AuditEvent, on_delete=models.PROTECT, related_name="changes")
    entity_type = models.CharField(max_length=60)
    entity_id = models.CharField(max_length=200)
    field = models.CharField(max_length=80)
    old_value = models.TextField(null=True, blank=True)  # noqa: DJ001 - NULL means "not set"
    new_value = models.TextField(null=True, blank=True)  # noqa: DJ001

    def __str__(self) -> str:
        return f"{self.entity_type}#{self.entity_id}.{self.field}"
