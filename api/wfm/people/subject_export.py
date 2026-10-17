"""Everything the system holds about one employee, for a subject-access request (NFR-03, POPIA).

Only the customer's admin may take it, and taking it is audited (who, whose, how many records; not
the contents). It is a file about a person, so it is sent `no-store`. Pay is the one exception to
"everything": a salary is never read back out of this system, so the file says whether pay is on
file and nothing about its amount, and the amounts of overtime and standby are left to payroll.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Q

from wfm.accounts.models import Role, User
from wfm.audit import services as audit
from wfm.audit.models import Action, AuditEvent
from wfm.core.errors import not_found
from wfm.notifications.models import Notification
from wfm.overtime.models import EmployeePay, OvertimeRequest, StandbyShift
from wfm.quality.models import QualityResult
from wfm.scheduling.models import Employee, ShiftAssignment
from wfm.telephony import subject as call_subject

from .models import Availability, LeaveRequest, SwapRequest

MAX_NOTIFICATIONS = 1000
MAX_AUDIT = 5000


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def build(admin: User, employee_id: int) -> tuple[dict[str, Any], int]:
    """The data and how many records are in it."""
    if admin.role != Role.ADMIN:
        raise not_found("No such employee.")
    found = (
        Employee.objects.for_user(admin)
        .select_related("manager", "user")
        .filter(pk=employee_id)
        .first()
    )
    if found is None:
        raise not_found("No such employee.")

    person: dict[str, Any] = {
        "employeeNumber": found.emp_no,
        "name": found.name,
        "contractType": found.contract_type,
        "weeklyHours": str(found.weekly_hours),
        "workMode": found.work_mode,
        "startDate": _iso(found.start_date),
        "endDate": _iso(found.end_date),
        "teamLead": found.manager.name if found.manager else None,
        "signInUsername": found.user.username if found.user else None,
        "signInRole": found.user.role if found.user else None,
        "agentLogins": [a.login for a in found.agent_logins.all()],
        "skills": [
            {"queue": s.queue.name, "level": s.level} for s in found.skills.select_related("queue")
        ],
        "credentials": [
            {"kind": c.kind, "name": c.name, "expiresOn": _iso(c.expires_on)}
            for c in found.credentials.all()
        ],
    }
    availability = [
        {
            "weekday": a.weekday,
            "from": a.start_time.isoformat(),
            "to": a.end_time.isoformat(),
            "kind": a.kind,
        }
        for a in Availability.objects.for_user(admin).filter(employee=found)
    ]
    leave = [
        {
            "type": r.leave_type.name,
            "from": r.start_date.isoformat(),
            "to": r.end_date.isoformat(),
            "days": r.days,
            "status": r.status,
            "asked": _iso(r.created_at),
        }
        for r in LeaveRequest.objects.for_user(admin)
        .filter(employee=found)
        .select_related("leave_type")
    ]
    shifts = [
        {
            "day": a.day.isoformat(),
            "shift": a.template.code,
            "queue": a.roster_week.queue.name,
            "rosterStatus": a.roster_week.status,
        }
        for a in ShiftAssignment.objects.for_user(admin)
        .filter(employee=found)
        .select_related("template", "roster_week__queue")
        .order_by("day")
    ]
    swaps = [
        {
            "queue": s.queue.name,
            "status": s.status,
            "gave": {"day": s.from_day.isoformat(), "shift": s.from_template.code}
            if s.from_employee_id == found.pk
            else None,
            "took": {"day": s.to_day.isoformat() if s.to_day else None}
            if s.to_employee_id == found.pk
            else None,
        }
        for s in SwapRequest.objects.for_user(admin)
        .filter(Q(from_employee=found) | Q(to_employee=found))
        .select_related("queue", "from_template")
    ]
    overtime = [
        {
            "day": o.day.isoformat(),
            "from": o.start_time.isoformat(),
            "to": o.end_time.isoformat(),
            "approvedMinutes": o.minutes,
            "status": o.status,
            "workedMinutes": o.worked_minutes,
            "reason": o.reason,
        }
        for o in OvertimeRequest.objects.for_user(admin).filter(employee=found)
    ]
    standby = [
        {
            "day": s.day.isoformat(),
            "status": s.status,
            "callOutMinutes": s.call_out_minutes,
        }
        for s in StandbyShift.objects.for_user(admin).filter(employee=found)
    ]
    quality = [
        {
            "date": r.evaluated_on.isoformat(),
            "kind": r.kind,
            "scorePct": float(r.score_pct),
            "csat": r.csat,
            "coachingDue": _iso(r.coaching_due),
        }
        for r in QualityResult.objects.for_user(admin)
        .filter(employee=found)
        .order_by("evaluated_on", "id")
    ]
    notifications = (
        [
            {"kind": n.kind, "message": n.message, "at": _iso(n.created_at)}
            for n in Notification.objects.filter(recipient=found.user).order_by("-created_at")[
                :MAX_NOTIFICATIONS
            ]
        ]
        if found.user
        else []
    )
    # What was done to them and by them, as the audit trail records it: what, when, outcome. Not
    # the chain hashes, and nothing about anybody else's record.
    mine = Q(subject_employee_id=found.pk)
    if found.user:
        mine |= Q(actor_user_id=found.user.pk)
    trail = [
        {
            "action": e.action,
            "at": _iso(e.occurred_at),
            "outcome": e.outcome,
            "actedBy": e.actor_role,
        }
        for e in AuditEvent.objects.filter(mine).order_by("-occurred_at")[:MAX_AUDIT]
    ]
    call_rows = call_subject.export_rows(person["agentLogins"])
    data = {
        "person": person,
        # Call data under this person's ACD logins: counts, their own offers and the transfers
        # they made. Never another agent's rows, a caller's number or a remark.
        "callData": call_rows["summary"],
        "callOffers": call_rows["offers"],
        "callTransfers": call_rows["transfers"],
        "pay": {
            "onFile": EmployeePay.objects.for_user(admin).filter(employee=found).exists(),
            "note": "Amounts are not held for export; ask payroll for pay figures.",
        },
        "availability": availability,
        "leave": leave,
        "shifts": shifts,
        "swaps": swaps,
        "overtime": overtime,
        "standby": standby,
        "qualityResults": quality,
        "notifications": notifications,
        "auditTrail": trail,
    }
    records = sum(len(v) for v in data.values() if isinstance(v, list)) + 1
    return data, records


def export(admin: User, employee_id: int) -> dict[str, Any]:
    """Build the export and record that it was taken, as the LAST write."""
    with transaction.atomic():
        data, records = build(admin, employee_id)
        audit.record(  # last write of the transaction
            actor=admin,
            action=Action.SUBJECT_EXPORTED,
            entity_type="employee",
            entity_id=str(employee_id),
            subject_employee_id=employee_id,
            changes=[
                audit.FieldChange("employee", str(employee_id), "records", None, str(records))
            ],
        )
    return data
