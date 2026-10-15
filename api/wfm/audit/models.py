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
    SSO_LOGIN = "auth.sso_login", "Signed in through an identity provider"
    SSO_DENIED = "auth.sso_denied", "Identity provider sign-in refused"
    IDENTITY_PROVISIONED = "identity.provisioned", "User created from a provider sign-in"
    IDENTITY_LINKED = "identity.linked", "Existing user linked to a provider identity"
    ROLE_CHANGED = "identity.role_changed", "Role changed by the provider's group mapping"
    ACCESS_DENIED = "access.denied", "Access denied"
    CDR_IMPORTED = "import.cdr", "Call detail report imported"
    CDR_IMPORT_REFUSED = "import.cdr_refused", "Call detail report import refused"
    DEV_DATA_PURGED = "dev.data_purged", "Synthetic development data purged"
    FORECAST_RUN = "forecast.run", "Forecast run"
    FORECAST_PUBLISHED = "forecast.published", "Forecast published"
    FORECAST_REFUSED = "forecast.refused", "Forecast request refused"
    FORECAST_TUNING_CHANGED = "forecast_tuning.changed", "Forecast tuning changed"
    FORECAST_EVENT_CREATED = "forecast_event.created", "Forecast event created"
    FORECAST_EVENT_CHANGED = "forecast_event.changed", "Forecast event changed"
    FORECAST_EVENT_DELETED = "forecast_event.deleted", "Forecast event deleted"
    LEAVE_REQUESTED = "leave.requested", "Leave requested"
    LEAVE_APPROVED = "leave.approved", "Leave approved"
    LEAVE_REJECTED = "leave.rejected", "Leave rejected"
    LEAVE_CANCELLED = "leave.cancelled", "Leave cancelled"
    LEAVE_ENTITLEMENT_CHANGED = "leave.entitlement_changed", "Leave entitlement changed"
    AVAILABILITY_ADDED = "availability.added", "Availability window added"
    AVAILABILITY_REMOVED = "availability.removed", "Availability window removed"
    SWAP_REQUESTED = "swap.requested", "Shift swap requested"
    SWAP_ACCEPTED = "swap.accepted", "Shift swap accepted by the colleague"
    SWAP_DECLINED = "swap.declined", "Shift swap declined by the colleague"
    SWAP_APPROVED = "swap.approved", "Shift swap approved"
    SWAP_REJECTED = "swap.rejected", "Shift swap rejected"
    SWAP_CANCELLED = "swap.cancelled", "Shift swap cancelled"
    WORKITEMS_IMPORTED = "workitems.imported", "Work items imported"
    WORKITEMS_IMPORT_REFUSED = "workitems.import_refused", "Work item import refused"
    SERVICE_POOL_CHANGED = "service_pool.changed", "Service pool settings changed"
    CAPACITY_LIMITS_CHANGED = "capacity.limits_changed", "Workforce limits changed"
    SHIFT_CREATED = "shift.created", "Shift template created"
    SHIFT_CHANGED = "shift.changed", "Shift template changed"
    SHIFT_DELETED = "shift.deleted", "Shift template deleted"
    EMPLOYEE_CREATED = "employee.created", "Employee created"
    EMPLOYEE_CHANGED = "employee.changed", "Employee changed"
    ROSTER_ASSIGNED = "roster.assigned", "Shift assigned"
    ROSTER_CLEARED = "roster.cleared", "Shift cleared"
    ROSTER_PUBLISHED = "roster.published", "Roster published"
    ROSTER_REOPENED = "roster.reopened", "Roster returned to draft"
    ROSTER_REFUSED = "roster.refused", "Roster change refused"
    ROSTER_EXPORTED = "roster.exported", "Roster exported"
    QUEUE_SETTINGS_CHANGED = "queue.settings_changed", "Queue staffing settings changed"
    CHAIN_BROKEN = "audit.chain_broken", "Audit chain integrity check failed"


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

    # Tamper evidence (AUD-10). All four are filled in by a database trigger at insert, never by
    # Python: see migrations/0003_hash_chain.py. Order of the chain is `chain_seq`, not `id`.
    chain_seq = models.BigIntegerField(unique=True, editable=False)
    prev_hash = models.CharField(max_length=64, editable=False)
    hash = models.CharField(max_length=64, editable=False)
    hash_version = models.PositiveSmallIntegerField(default=1, editable=False)

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
    hash = models.CharField(
        max_length=64, editable=False
    )  # set by a trigger, covers the event's hash

    def __str__(self) -> str:
        return f"{self.entity_type}#{self.entity_id}.{self.field}"
