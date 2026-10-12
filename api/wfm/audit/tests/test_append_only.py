"""The audit trail must be tamper-resistant in the database itself (AUD-08, AUD-09)."""

from __future__ import annotations

import pytest
from django.db import DatabaseError, connection, transaction

from wfm.accounts.models import Role, User
from wfm.audit import services as audit
from wfm.audit.models import Action, AuditChange, AuditEvent, Outcome

pytestmark = pytest.mark.django_db


def make_event() -> AuditEvent:
    return audit.record(actor=None, action=Action.LOGOUT)


def test_record_has_no_timestamp_parameter() -> None:
    with pytest.raises(TypeError):
        audit.record(actor=None, action=Action.LOGOUT, occurred_at="2020-01-01")  # type: ignore[call-arg]


def test_system_actor_when_no_user() -> None:
    event = make_event()
    assert event.actor_type == "system"
    assert event.actor_user_id is None


def test_user_actor_records_role_at_that_moment() -> None:
    user = User.objects.create_user(username="lee", password="x", role=Role.LEAD)
    event = audit.record(actor=user, action=Action.LOGOUT)

    user.role = Role.ADMIN
    user.save()

    event.refresh_from_db()
    assert event.actor_role == "lead"  # unchanged: history keeps the role held at the time


def test_field_level_changes_are_stored() -> None:
    event = audit.record(
        actor=None,
        action=Action.LOGOUT,
        changes=[audit.FieldChange("leave", "42", "status", "pending", "approved")],
    )
    (change,) = event.changes.all()
    assert (change.field, change.old_value, change.new_value) == ("status", "pending", "approved")


def test_update_is_blocked_by_the_database() -> None:
    event = make_event()
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).update(outcome=Outcome.FAILED)


def test_delete_is_blocked_by_the_database() -> None:
    event = make_event()
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        AuditEvent.objects.filter(pk=event.pk).delete()


def test_truncate_is_blocked_by_the_database() -> None:
    make_event()
    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("TRUNCATE audit_auditevent CASCADE")


def test_changes_table_is_append_only_too() -> None:
    event = audit.record(
        actor=None,
        action=Action.LOGOUT,
        changes=[audit.FieldChange("leave", "1", "status", None, "pending")],
    )
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        AuditChange.objects.filter(event=event).update(new_value="tampered")


class ChangeFailedError(Exception):
    pass


def _audited_change_that_fails() -> None:
    with transaction.atomic():
        make_event()
        raise ChangeFailedError


def test_audit_rolls_back_with_the_change_it_belongs_to() -> None:
    """AUD-08: no change without its audit event, and no audit event for a rolled-back change."""
    with pytest.raises(ChangeFailedError):
        _audited_change_that_fails()

    assert AuditEvent.objects.count() == 0
