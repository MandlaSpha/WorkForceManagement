from __future__ import annotations

from datetime import date

from django.http import HttpRequest, HttpResponse
from ninja import Router, Status
from wfm_engine.roster import is_overnight, shift_kind, shift_minutes

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import roster_services, selectors, services
from .models import Employee, RosterWeek, ShiftTemplate
from .policy import EMPLOYEE_WRITE_ROLES, READ_ROLES, ROSTER_WRITE_ROLES, SHIFT_WRITE_ROLES
from .schemas import (
    AssignIn,
    AssignOut,
    EmployeeIn,
    EmployeeOut,
    PlanCellOut,
    PlanForecastOut,
    PlanOut,
    PlanSummaryOut,
    RosterCellOut,
    RosterOut,
    RosterRowOut,
    ShiftIn,
    ShiftOut,
    SkillOut,
    WeekIn,
    WeekOut,
    WorstOut,
)

router = Router(tags=["scheduling"])

FEATURE = Feature.SCHEDULING
READ = RoleSessionAuth(*sorted(READ_ROLES), feature=FEATURE)
SHIFT_WRITE = RoleSessionAuth(*sorted(SHIFT_WRITE_ROLES), feature=FEATURE)
EMPLOYEE_WRITE = RoleSessionAuth(*sorted(EMPLOYEE_WRITE_ROLES), feature=FEATURE)
ROSTER_WRITE = RoleSessionAuth(*sorted(ROSTER_WRITE_ROLES), feature=FEATURE)


# --- shift templates ---------------------------------------------------------------------------


@router.get("/shifts", auth=READ, response=list[ShiftOut], summary="The shift library")
def list_shifts(request: HttpRequest) -> list[ShiftOut]:
    return [_shift_out(s) for s in selectors.shifts(current_user(request))]


@router.post("/shifts", auth=SHIFT_WRITE, response={201: ShiftOut}, summary="Add a shift")
def create_shift(request: HttpRequest, body: ShiftIn) -> Status[ShiftOut]:
    shift = services.create_shift(
        user=current_user(request),
        code=body.code,
        start_time=body.startTime,
        end_time=body.endTime,
        paid_minutes=body.paidMinutes,
    )
    return Status(201, _shift_out(shift))


@router.put("/shifts/{shift_id}", auth=SHIFT_WRITE, response=ShiftOut, summary="Change a shift")
def update_shift(request: HttpRequest, shift_id: int, body: ShiftIn) -> ShiftOut:
    shift = services.update_shift(
        user=current_user(request),
        shift_id=shift_id,
        code=body.code,
        start_time=body.startTime,
        end_time=body.endTime,
        paid_minutes=body.paidMinutes,
    )
    return _shift_out(shift)


@router.delete(
    "/shifts/{shift_id}", auth=SHIFT_WRITE, response=dict[str, bool], summary="Delete a shift"
)
def delete_shift(request: HttpRequest, shift_id: int) -> dict[str, bool]:
    services.delete_shift(user=current_user(request), shift_id=shift_id)
    return {"ok": True}


# --- employees ---------------------------------------------------------------------------------


@router.get("/employees", auth=READ, response=list[EmployeeOut], summary="Employees")
def list_employees(request: HttpRequest, queue_id: int | None = None) -> list[EmployeeOut]:
    return [_employee_out(e) for e in selectors.employees(current_user(request), queue_id)]


@router.post(
    "/employees", auth=EMPLOYEE_WRITE, response={201: EmployeeOut}, summary="Add an employee"
)
def create_employee(request: HttpRequest, body: EmployeeIn) -> Status[EmployeeOut]:
    employee = services.create_employee(
        user=current_user(request),
        emp_no=body.empNo,
        name=body.name,
        contract_type=body.contractType,
        work_mode=body.workMode,
        weekly_hours=body.weeklyHours,
        start_date=body.startDate,
        end_date=body.endDate,
        skills=[services.SkillInput(s.queueId, s.level) for s in body.skills],
    )
    return Status(201, _employee_out(employee))


@router.put(
    "/employees/{employee_id}",
    auth=EMPLOYEE_WRITE,
    response=EmployeeOut,
    summary="Change an employee",
)
def update_employee(request: HttpRequest, employee_id: int, body: EmployeeIn) -> EmployeeOut:
    employee = services.update_employee(
        user=current_user(request),
        employee_id=employee_id,
        emp_no=body.empNo,
        name=body.name,
        contract_type=body.contractType,
        work_mode=body.workMode,
        weekly_hours=body.weeklyHours,
        start_date=body.startDate,
        end_date=body.endDate,
        skills=[services.SkillInput(s.queueId, s.level) for s in body.skills],
    )
    return _employee_out(employee)


# --- the roster --------------------------------------------------------------------------------


@router.get("/roster", auth=READ, response=RosterOut, summary="One queue's roster for a week")
def roster(request: HttpRequest, queue_id: int, week_start: date) -> RosterOut:
    grid = selectors.roster_grid(current_user(request), queue_id, week_start)
    days = selectors.week_days(week_start)
    return RosterOut(
        queueId=grid.queue.pk,
        queue=grid.queue.name,
        weekStart=week_start,
        days=days,
        status=grid.status,
        publishedAt=grid.published_at,
        rows=[
            RosterRowOut(
                employeeId=r.employee.pk,
                empNo=r.employee.emp_no,
                name=r.employee.name,
                weeklyHours=float(r.employee.weekly_hours),
                daysWorked=r.days_worked,
                paidMinutes=r.paid_minutes,
                cells=[
                    RosterCellOut(day=d, shiftId=t.pk, code=t.code)
                    for d, t in sorted(r.cells.items())
                ],
            )
            for r in grid.rows
        ],
        onCounts={d.isoformat(): n for d, n in grid.on_counts.items()},
        shifts=[_shift_out(s) for s in grid.shifts],
    )


@router.put(
    "/roster/assignments",
    auth=ROSTER_WRITE,
    response=AssignOut,
    summary="Put a person on a shift, or clear it",
)
def assign(request: HttpRequest, body: AssignIn) -> AssignOut:
    result = roster_services.assign(
        user=current_user(request),
        queue_id=body.queueId,
        employee_id=body.employeeId,
        day=body.day,
        template_id=body.templateId,
    )
    shift = result.assignment.template if result.assignment else None
    return AssignOut(
        employeeId=body.employeeId,
        day=body.day,
        shiftId=shift.pk if shift else None,
        code=shift.code if shift else None,
        weekStatus=result.week.status,
    )


@router.post(
    "/roster/publish", auth=ROSTER_WRITE, response=WeekOut, summary="Publish a week's roster"
)
def publish(request: HttpRequest, body: WeekIn) -> WeekOut:
    week = roster_services.publish(
        user=current_user(request), queue_id=body.queueId, week_start=body.weekStart
    )
    return _week_out(week)


@router.post(
    "/roster/reopen",
    auth=ROSTER_WRITE,
    response=WeekOut,
    summary="Return a published week to draft",
)
def reopen(request: HttpRequest, body: WeekIn) -> WeekOut:
    week = roster_services.reopen(
        user=current_user(request), queue_id=body.queueId, week_start=body.weekStart
    )
    return _week_out(week)


@router.get(
    "/roster/export.csv", auth=READ, response={200: None}, summary="Export a week's roster as CSV"
)
def export_roster(request: HttpRequest, queue_id: int, week_start: date) -> HttpResponse:
    name, text = roster_services.export_csv(
        user=current_user(request), queue_id=queue_id, week_start=week_start
    )
    response = HttpResponse(text, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


# --- the plan ----------------------------------------------------------------------------------


@router.get(
    "/plan", auth=READ, response=PlanOut, summary="Scheduled against required, per half-hour"
)
def plan(request: HttpRequest, queue_id: int, week_start: date) -> PlanOut:
    found = selectors.week_plan(current_user(request), queue_id, week_start)
    summary = found.summary
    worst = None
    if summary.worst is not None:
        (day, slot), gap = summary.worst
        worst = WorstOut(day=day, slot=slot, variance=gap)
    version = found.forecast
    return PlanOut(
        queueId=found.queue.pk,
        queue=found.queue.name,
        weekStart=week_start,
        days=selectors.week_days(week_start),
        rosterStatus=found.roster_status,
        forecast=PlanForecastOut(
            id=str(version.id),
            label=version.label,
            publishedAt=version.published_at,
            assumptionsConfirmed=bool(version.params.get("assumptionsConfirmed")),
        )
        if version
        else None,
        cells={
            day.isoformat(): [
                PlanCellOut(
                    slot=c.slot,
                    scheduled=c.scheduled,
                    required=c.required,
                    variance=c.variance,
                    state=c.state,
                )
                for c in cells
            ]
            for day, cells in found.cells.items()
        },
        summary=PlanSummaryOut(
            intervalsKnown=summary.intervals_known,
            underIntervals=summary.under_intervals,
            gap=summary.gap,
            requiredTotal=summary.required_total,
            scheduledTotal=summary.scheduled_total,
            worst=worst,
        ),
    )


# --- shaping -----------------------------------------------------------------------------------


def _shift_out(shift: ShiftTemplate) -> ShiftOut:
    return ShiftOut(
        id=shift.pk,
        code=shift.code,
        startTime=f"{shift.start_time:%H:%M}",
        endTime=f"{shift.end_time:%H:%M}",
        paidMinutes=shift.paid_minutes,
        minutes=shift_minutes(shift.start_time, shift.end_time),
        overnight=is_overnight(shift.start_time, shift.end_time),
        kind=shift_kind(shift.start_time, shift.end_time),
    )


def _employee_out(employee: Employee) -> EmployeeOut:
    return EmployeeOut(
        id=employee.pk,
        empNo=employee.emp_no,
        name=employee.name,
        contractType=employee.contract_type,
        workMode=employee.work_mode,
        weeklyHours=float(employee.weekly_hours),
        weeklyHoursIsDefault=employee.weekly_hours_is_default,
        startDate=employee.start_date,
        endDate=employee.end_date,
        skills=[
            SkillOut(queueId=s.queue_id, queue=s.queue.name, level=s.level)
            for s in employee.skills.select_related("queue").order_by("queue__name")
        ],
    )


def _week_out(week: RosterWeek) -> WeekOut:
    return WeekOut(
        queueId=week.queue_id,
        weekStart=week.week_start,
        status=week.status,
        publishedAt=week.published_at,
    )
