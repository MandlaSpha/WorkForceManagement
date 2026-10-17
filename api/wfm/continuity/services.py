"""Writes for backup teams (BCP-01). The audit event is the LAST write of each transaction."""

from __future__ import annotations

from django.db import IntegrityError, transaction

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found
from wfm.scheduling.models import Employee
from wfm.telephony.models import Queue

from .models import BackupMember, BackupTeam

MAX_NAME = 100


def _refuse(status: int, code: str, detail: str) -> ApiError:
    return ApiError(status, code, "Backup team refused", detail)


def create_team(*, user: User, queue_id: int, name: str) -> BackupTeam:
    clean = name.strip()
    if not clean or len(clean) > MAX_NAME:
        raise _refuse(
            422, "continuity.name_invalid", f"Give the team a name of 1 to {MAX_NAME} characters."
        )
    queue = Queue.objects.for_user(user).filter(pk=queue_id).first()
    if queue is None:
        raise not_found("No such queue.")
    try:
        with transaction.atomic():
            team = BackupTeam.objects.create(queue=queue, name=clean, created_by=user)
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.BACKUP_TEAM_CREATED,
                entity_type="backup_team",
                entity_id=str(team.pk),
                changes=[
                    audit.FieldChange("backup_team", str(team.pk), "queue", None, queue.name),
                    audit.FieldChange("backup_team", str(team.pk), "name", None, clean),
                ],
            )
    except IntegrityError:
        raise _refuse(
            409, "continuity.name_taken", "That queue already has a team of that name."
        ) from None
    return team


def delete_team(*, user: User, team_id: int) -> None:
    with transaction.atomic():
        team = (
            BackupTeam.objects.select_for_update(of=("self",), no_key=True)
            .for_user(user)
            .select_related("queue")
            .filter(pk=team_id)
            .first()
        )
        if team is None:
            raise not_found("No such backup team.")
        pk, name, queue_name = team.pk, team.name, team.queue.name
        team.delete()
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.BACKUP_TEAM_DELETED,
            entity_type="backup_team",
            entity_id=str(pk),
            changes=[
                audit.FieldChange("backup_team", str(pk), "queue", queue_name, None),
                audit.FieldChange("backup_team", str(pk), "name", name, None),
            ],
        )


def add_member(*, user: User, team_id: int, employee_id: int) -> BackupMember:
    with transaction.atomic():
        team = (
            BackupTeam.objects.select_for_update(of=("self",), no_key=True)
            .for_user(user)
            .filter(pk=team_id)
            .first()
        )
        employee = Employee.objects.for_user(user).filter(pk=employee_id).first()
        if team is None or employee is None:
            raise not_found("No such team or person.")
        if BackupMember.objects.filter(team=team, employee=employee).exists():
            raise _refuse(409, "continuity.already_member", "That person is already on the team.")
        member = BackupMember.objects.create(team=team, employee=employee, added_by=user)
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.BACKUP_MEMBER_ADDED,
            entity_type="backup_team",
            entity_id=str(team.pk),
            subject_employee_id=employee.pk,
            changes=[
                audit.FieldChange("backup_team", str(team.pk), "member", None, str(employee.pk))
            ],
        )
    return member


def remove_member(*, user: User, team_id: int, employee_id: int) -> None:
    with transaction.atomic():
        member = (
            BackupMember.objects.select_for_update(of=("self",), no_key=True)
            .for_user(user)
            .filter(team_id=team_id, employee_id=employee_id)
            .first()
        )
        if member is None:
            raise not_found("No such person on that team.")
        member.delete()
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.BACKUP_MEMBER_REMOVED,
            entity_type="backup_team",
            entity_id=str(team_id),
            subject_employee_id=employee_id,
            changes=[
                audit.FieldChange("backup_team", str(team_id), "member", str(employee_id), None)
            ],
        )
