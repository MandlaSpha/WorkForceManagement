from __future__ import annotations

from datetime import date

from django.http import HttpRequest, HttpResponse
from ninja import File, Router, Status
from ninja.files import UploadedFile
from wfm_engine.roster import is_overnight, shift_kind, shift_minutes

from wfm.accounts.models import Role
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import import_services, roster_services, selectors, services
from .models import Employee, RosterWeek, ShiftTemplate
from .policy import (
    EMPLOYEE_WRITE_ROLES,
    MANAGER_ROLES,
    READ_ROLES,
    ROSTER_WRITE_ROLES,
    SHIFT_WRITE_ROLES,
)
from .schemas import (
    AgentLoginsIn,
    AssignIn,
    AssignOut,
    AttentionOut,
    EmployeeImportOut,
    EmployeeIn,
    EmployeeLoginIn,
    EmployeeOut,
    OverviewDayOut,
    OverviewOut,
    OverviewQueueOut,
    OverviewTotalsOut,
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
    UnmappedLoginOut,
    WeekIn,
    WeekOut,
    WorstOut,
)

router = Router(tags=["scheduling"])

FEATURE = Feature.SCHEDULING
READ = RoleSessionAuth(*sorted(READ_ROLES), feature=FEATURE)
SHIFT_WRITE = RoleSessionAuth(*sorted(SHIFT_WRITE_ROLES), feature=FEATURE)
EMPLOYEE_WRITE = RoleSessionAuth(*sorted(EMPLOYEE_WRITE_ROLES), feature=FEATURE)
# Tying a login to a person decides whose schedule it opens, so only the customer's admin does it.
ADMIN_ONLY = RoleSessionAuth(Role.ADMIN, feature=FEATURE)
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


@router.get(
    "/overview",
    auth=READ,
    response=OverviewOut,
    summary="Every queue's week at a glance: gap, rosters and what needs attention",
)
def get_overview(request: HttpRequest, week_start: date) -> OverviewOut:
    result = selectors.overview(current_user(request), week_start)
    queues = []
    for plan in result.plans:
        worst = plan.summary.worst
        # A published forecast that does not reach this week is no forecast for it.
        covered = plan.forecast if plan.summary.intervals_known > 0 else None
        queues.append(
            OverviewQueueOut(
                queueId=plan.queue.pk,
                queue=plan.queue.name,
                rosterStatus=plan.roster_status,
                forecastLabel=None if covered is None else covered.label,
                assumptionsConfirmed=(
                    None if covered is None else bool(covered.params.get("assumptionsConfirmed"))
                ),
                intervalsKnown=plan.summary.intervals_known,
                underIntervals=plan.summary.under_intervals,
                gap=plan.summary.gap,
                requiredTotal=plan.summary.required_total,
                scheduledTotal=plan.summary.scheduled_total,
                worstVariance=None if worst is None else worst[1],
                worstDay=None if worst is None else worst[0][0],
                worstSlot=None if worst is None else worst[0][1],
            )
        )
    return OverviewOut(
        weekStart=result.week_start,
        totals=OverviewTotalsOut(
            queues=len(result.plans),
            queuesWithForecast=sum(1 for p in result.plans if p.summary.intervals_known > 0),
            intervalsKnown=sum(p.summary.intervals_known for p in result.plans),
            underIntervals=sum(p.summary.under_intervals for p in result.plans),
            gap=sum(p.summary.gap for p in result.plans),
            headcount=result.headcount,
            rostersPublished=sum(1 for p in result.plans if p.roster_status == "published"),
        ),
        queues=queues,
        days=[
            OverviewDayOut(day=d.day, gap=d.gap, underIntervals=d.under_intervals)
            for d in result.days
        ],
        attention=[
            AttentionOut(
                severity=i.severity,
                kind=i.kind,
                queueId=i.queue_id,
                queue=i.queue,
                text=i.text,
                count=i.count,
            )
            for i in result.attention
        ],
    )


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
        manager_id=body.managerId,
    )
    return Status(201, _employee_out(employee))


# Declared before the routes that take an employee id: otherwise 'import' would be read as one.
@router.post(
    "/employees/import",
    auth=EMPLOYEE_WRITE,
    response=EmployeeImportOut,
    summary="Import the employee master from a CSV or Excel file (dry_run shows what would happen)",
)
def import_employees(
    request: HttpRequest, file: File[UploadedFile], dry_run: bool = True
) -> EmployeeImportOut:
    report = import_services.import_employees(
        user=current_user(request),
        content=file.read(),
        filename=file.name or "",
        dry_run=dry_run,
    )
    return EmployeeImportOut(
        dryRun=report.dry_run,
        created=report.created,
        updated=report.updated,
        unchanged=report.unchanged,
        rejected=dict(report.rejected),
        ignoredColumns=report.ignored_columns,
        loginsMapped=report.logins_mapped,
    )


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
        manager_id=body.managerId if "managerId" in body.model_fields_set else services.KEEP,
    )
    return _employee_out(employee)


@router.get(
    "/agent-logins/unmapped",
    auth=EMPLOYEE_WRITE,
    response=list[UnmappedLoginOut],
    summary="ACD logins seen on calls that belong to nobody yet",
)
def unmapped_logins(request: HttpRequest) -> list[UnmappedLoginOut]:
    return [
        UnmappedLoginOut(login=u.login, calls=u.calls) for u in import_services.unmapped_logins()
    ]


@router.put(
    "/employees/{employee_id}/agent-logins",
    auth=EMPLOYEE_WRITE,
    response=EmployeeOut,
    summary="Set the ACD logins that are this person",
)
def set_agent_logins(request: HttpRequest, employee_id: int, body: AgentLoginsIn) -> EmployeeOut:
    return _employee_out(
        import_services.set_agent_logins(
            user=current_user(request), employee_id=employee_id, logins=body.logins
        )
    )


@router.put(
    "/employees/{employee_id}/login",
    auth=ADMIN_ONLY,
    response=EmployeeOut,
    summary="Link an employee to the login they sign in with, or unlink it",
)
def link_login(request: HttpRequest, employee_id: int, body: EmployeeLoginIn) -> EmployeeOut:
    return _employee_out(
        services.link_login(
            actor=current_user(request), employee_id=employee_id, user_id=body.userId
        )
    )


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
        managerId=employee.manager_id,
        manager=employee.manager.name if employee.manager else None,
        canManage=employee.user is not None and employee.user.role in MANAGER_ROLES,
        hasLogin=employee.user_id is not None,
        agentLogins=[a.login for a in employee.agent_logins.all()],
    )


def _week_out(week: RosterWeek) -> WeekOut:
    return WeekOut(
        queueId=week.queue_id,
        weekStart=week.week_start,
        status=week.status,
        publishedAt=week.published_at,
    )
