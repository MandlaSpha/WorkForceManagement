"""Business continuity: backup teams per queue and the mobilise view (BCP-01)."""

from __future__ import annotations

from datetime import date

from django.http import HttpRequest
from ninja import Router, Schema, Status
from wfm_engine import continuity as engine

from wfm.core.errors import ApiError
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user
from wfm.scheduling.models import Employee

from . import selectors, services
from .policy import DEFAULT_LOST_PCT, READ_ROLES, WRITE_ROLES

router = Router(tags=["continuity"])
FEATURE = Feature.PEOPLE
READ = RoleSessionAuth(*sorted(READ_ROLES), feature=FEATURE)
WRITE = RoleSessionAuth(*sorted(WRITE_ROLES), feature=FEATURE)


class BackupPersonOut(Schema):
    employeeId: int  # noqa: N815
    empNo: str  # noqa: N815
    employee: str
    workMode: str  # noqa: N815 - office, hybrid or remote: the remote-work flag
    remoteCapable: bool  # noqa: N815


class BackupTeamOut(Schema):
    id: int
    queueId: int  # noqa: N815
    queue: str
    name: str
    memberCount: int  # noqa: N815
    members: list[BackupPersonOut]  # empty for a reader who may not see names


class BackupTeamIn(Schema):
    queueId: int  # noqa: N815
    name: str


class BackupMemberIn(Schema):
    employeeId: int  # noqa: N815


class MobiliseCandidateOut(BackupPersonOut):
    status: str  # free, rostered_elsewhere, already_rostered, on_leave, unavailable, needs_office
    usable: bool


class MobiliseTeamOut(Schema):
    teamId: int  # noqa: N815
    name: str
    memberCount: int  # noqa: N815
    usableCount: int  # noqa: N815
    candidates: list[MobiliseCandidateOut]  # empty for a reader who may not see names


class MobiliseImpactOut(Schema):
    rostered: int
    lost: int
    remaining: int
    recovered: int
    coveredAfter: int  # noqa: N815
    shortfall: int
    coveragePct: float | None  # noqa: N815


class MobiliseOut(Schema):
    queue: str
    day: date
    scenario: str
    lostPct: int  # noqa: N815
    rosteredByMode: dict[str, int]  # noqa: N815
    impact: MobiliseImpactOut
    byStatus: dict[str, int]  # noqa: N815
    usableDistinct: int  # noqa: N815 - distinct people, even when on more than one team
    teams: list[MobiliseTeamOut]


def _person(e: Employee) -> dict[str, object]:
    mode = e.work_mode
    return {
        "employeeId": e.pk,
        "empNo": e.emp_no,
        "employee": e.name,
        "workMode": mode,
        "remoteCapable": mode in engine.REMOTE_CAPABLE,
    }


def _team(view: selectors.TeamView) -> BackupTeamOut:
    return BackupTeamOut(
        id=view.team.pk,
        queueId=view.team.queue_id,
        queue=view.queue_name,
        name=view.team.name,
        memberCount=view.member_count,
        members=[BackupPersonOut(**_person(e)) for e in view.members],  # type: ignore[arg-type]
    )


@router.get(
    "/teams",
    auth=READ,
    response=list[BackupTeamOut],
    summary="Backup teams, optionally for one queue (an executive: counts, no names)",
)
def list_teams(request: HttpRequest, queue_id: int | None = None) -> list[BackupTeamOut]:
    return [_team(v) for v in selectors.teams(current_user(request), queue_id=queue_id)]


@router.post(
    "/teams",
    auth=WRITE,
    response={201: BackupTeamOut},
    summary="Name a backup team for a queue",
)
def create_team(request: HttpRequest, body: BackupTeamIn) -> Status[BackupTeamOut]:
    user = current_user(request)
    team = services.create_team(user=user, queue_id=body.queueId, name=body.name)
    return Status(201, _team(selectors.teams(user, team_id=team.pk)[0]))


@router.delete(
    "/teams/{team_id}", auth=WRITE, response=dict[str, bool], summary="Delete a backup team"
)
def delete_team(request: HttpRequest, team_id: int) -> dict[str, bool]:
    services.delete_team(user=current_user(request), team_id=team_id)
    return {"ok": True}


@router.post(
    "/teams/{team_id}/members",
    auth=WRITE,
    response={201: BackupTeamOut},
    summary="Add a person to a backup team",
)
def add_member(request: HttpRequest, team_id: int, body: BackupMemberIn) -> Status[BackupTeamOut]:
    user = current_user(request)
    services.add_member(user=user, team_id=team_id, employee_id=body.employeeId)
    return Status(201, _team(selectors.teams(user, team_id=team_id)[0]))


@router.delete(
    "/teams/{team_id}/members/{employee_id}",
    auth=WRITE,
    response=dict[str, bool],
    summary="Remove a person from a backup team",
)
def remove_member(request: HttpRequest, team_id: int, employee_id: int) -> dict[str, bool]:
    services.remove_member(user=current_user(request), team_id=team_id, employee_id=employee_id)
    return {"ok": True}


@router.get(
    "/mobilise",
    auth=READ,
    response=MobiliseOut,
    summary="Who on the backup teams could cover a failed site or outbreak, and the roster impact",
)
def get_mobilise(
    request: HttpRequest,
    queue_id: int,
    day: date,
    scenario: str = engine.SITE,
    lost_pct: int = DEFAULT_LOST_PCT,
) -> MobiliseOut:
    if scenario not in engine.SCENARIOS:
        raise ApiError(
            422, "continuity.scenario_invalid", "Unknown scenario", "Choose 'site' or 'outbreak'."
        )
    if not 0 <= lost_pct <= 100:
        raise ApiError(
            422, "continuity.lost_pct_invalid", "Bad percentage", "lost_pct is 0 to 100."
        )
    found = selectors.mobilise(current_user(request), queue_id, day, scenario, lost_pct)
    i = found.impact
    return MobiliseOut(
        queue=found.queue_name,
        day=found.day,
        scenario=found.scenario,
        lostPct=found.lost_pct,
        rosteredByMode=found.rostered_by_mode,
        impact=MobiliseImpactOut(
            rostered=i.rostered,
            lost=i.lost,
            remaining=i.remaining,
            recovered=i.recovered,
            coveredAfter=i.covered_after,
            shortfall=i.shortfall,
            coveragePct=i.coverage_pct,
        ),
        byStatus=found.by_status,
        usableDistinct=found.usable_distinct,
        teams=[
            MobiliseTeamOut(
                teamId=t.team_id,
                name=t.name,
                memberCount=t.member_count,
                usableCount=t.usable_count,
                candidates=[
                    MobiliseCandidateOut(
                        **_person(c.employee),  # type: ignore[arg-type]
                        status=c.status,
                        usable=c.usable,
                    )
                    for c in t.candidates
                ],
            )
            for t in found.teams
        ],
    )
