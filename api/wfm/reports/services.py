"""Making, changing and sending report schedules (RPT-04, RPT-10).

Safeguards, each tested: a report holds only what its owner may see (it is built as the owner, with
the same scoping as the screen); recipients are limited to domains the admin allowed, checked when
a schedule is made AND when it sends; making, changing, sending and failing are audited without any
address or figure; and a schedule stops if its owner is deactivated. Writes are one transaction with
the audit event as the LAST write.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from wfm_engine import schedule as rules

from wfm.accounts.models import Role, User
from wfm.audit import services as audit
from wfm.audit.models import Action, ActorType
from wfm.audit.models import Outcome as AuditOutcome
from wfm.core.errors import ApiError, not_found
from wfm.telephony.models import Queue

from . import renderers
from .models import Frequency, Outcome, ReportKind, ReportSchedule, ReportSettings

log = logging.getLogger(__name__)

MAX_RECIPIENTS = 10
MAX_SCHEDULES_PER_PERSON = 20
SCORECARD_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS})
PEAKS_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.LEAD, Role.EXECUTIVE, Role.CUSTOMER_OPS})
# The board pack is for executives and the planning roles; customer operations get the queue
# figures of their own contracts (and never the hiring sheet).
BOARD_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS})
ROLES_FOR = {
    ReportKind.SCORECARD: SCORECARD_ROLES,
    ReportKind.PEAKS: PEAKS_ROLES,
    ReportKind.BOARD: BOARD_ROLES,
}
MAX_DOMAINS = 50


def _refuse(status: int, code: str, detail: str) -> ApiError:
    return ApiError(status, code, "Report schedule refused", detail)


def allowed_domains() -> list[str]:
    row = ReportSettings.objects.filter(pk=1).first()
    return sorted(row.allowed_domains) if row else []


def _domain_of(address: str) -> str:
    return address.rsplit("@", 1)[-1].lower()


def clean_recipients(raw: list[str]) -> list[str]:
    """Valid, de-duplicated addresses on an allowed domain; anything else is refused with a reason
    that names the address (the person typed it) but not the list of allowed domains."""
    cleaned: list[str] = []
    for item in raw:
        address = item.strip().lower()
        if not address:
            continue
        try:
            validate_email(address)
        except ValidationError as bad:
            raise _refuse(
                422, "report.bad_address", f"{address!r} is not an email address."
            ) from bad
        if address not in cleaned:
            cleaned.append(address)
    if not cleaned:
        raise _refuse(422, "report.no_recipients", "Give at least one email address.")
    if len(cleaned) > MAX_RECIPIENTS:
        raise _refuse(422, "report.too_many", f"At most {MAX_RECIPIENTS} addresses.")
    allowed = set(allowed_domains())
    if not allowed:
        raise _refuse(
            409,
            "report.no_domains",
            "No email domain has been allowed yet. Ask your administrator to allow one.",
        )
    for address in cleaned:
        if _domain_of(address) not in allowed:
            raise _refuse(
                422,
                "report.domain_not_allowed",
                f"{address} is not on a domain your administrator has allowed.",
            )
    return cleaned


def _check_shape(
    user: User,
    report: str,
    queue_id: int | None,
    frequency: str,
    hour: int,
    weekday: int,
    day_of_month: int,
) -> Queue | None:
    if report not in ReportKind.values:
        raise _refuse(422, "report.unknown", "That report does not exist.")
    if user.role not in ROLES_FOR[ReportKind(report)]:
        raise _refuse(403, "auth.forbidden", "Your role may not schedule that report.")
    if frequency not in Frequency.values:
        raise _refuse(422, "report.bad_frequency", "Choose daily, weekly or monthly.")
    if not 0 <= hour <= 23:
        raise _refuse(422, "report.bad_time", "The hour is 0 to 23.")
    if not 0 <= weekday <= 6:
        raise _refuse(422, "report.bad_day", "The weekday is Monday (0) to Sunday (6).")
    if not 1 <= day_of_month <= rules.MAX_MONTH_DAY:
        raise _refuse(422, "report.bad_day", "The day of the month is 1 to 28.")
    queue: Queue | None = None
    if report == ReportKind.PEAKS:
        queue = Queue.objects.for_user(user).filter(pk=queue_id).first() if queue_id else None
        if queue is None:
            raise not_found("No such queue.")
    return queue


def create(
    *,
    user: User,
    report: str,
    queue_id: int | None,
    recipients: list[str],
    frequency: str,
    hour: int,
    weekday: int = 0,
    day_of_month: int = 1,
) -> ReportSchedule:
    queue = _check_shape(user, report, queue_id, frequency, hour, weekday, day_of_month)
    with transaction.atomic():
        if ReportSchedule.objects.filter(owner=user).count() >= MAX_SCHEDULES_PER_PERSON:
            raise _refuse(
                409, "report.too_many_schedules", "That is enough schedules for one person."
            )
        made = ReportSchedule.objects.create(
            owner=user,
            report=report,
            queue=queue,
            recipients=clean_recipients(recipients),
            frequency=frequency,
            hour=hour,
            weekday=weekday,
            day_of_month=day_of_month,
        )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.REPORT_SCHEDULE_CREATED,
            entity_type="report_schedule",
            entity_id=str(made.pk),
            changes=[
                audit.FieldChange("report_schedule", str(made.pk), "report", None, report),
                audit.FieldChange(
                    "report_schedule", str(made.pk), "recipients", None, str(len(made.recipients))
                ),
            ],
        )
    return made


def _mine(user: User, schedule_id: int) -> ReportSchedule:
    found: ReportSchedule | None = (
        ReportSchedule.objects.select_for_update(no_key=True, of=("self",))
        .for_user(user)
        .select_related("owner", "queue")
        .filter(pk=schedule_id)
        .first()
    )
    if found is None:
        raise not_found("No such report schedule.")
    return found


def update(
    *,
    user: User,
    schedule_id: int,
    recipients: list[str] | None = None,
    frequency: str | None = None,
    hour: int | None = None,
    weekday: int | None = None,
    day_of_month: int | None = None,
    paused: bool | None = None,
) -> ReportSchedule:
    """Change when and to whom a schedule sends, or pause or resume it. Only its owner changes
    what it sends and to whom; the admin may also pause it (never read or redirect it)."""
    with transaction.atomic():
        found = _mine(user, schedule_id)
        is_owner = found.owner_id == user.pk
        changing_content = any(
            v is not None for v in (recipients, frequency, hour, weekday, day_of_month)
        )
        if changing_content and not is_owner:
            raise not_found("No such report schedule.")
        what: list[str] = []
        if changing_content:
            _check_shape(
                user,
                found.report,
                found.queue_id,
                frequency or found.frequency,
                found.hour if hour is None else hour,
                found.weekday if weekday is None else weekday,
                found.day_of_month if day_of_month is None else day_of_month,
            )
            if recipients is not None:
                found.recipients = clean_recipients(recipients)
                what.append("recipients")
            if frequency is not None:
                found.frequency = frequency
                what.append("frequency")
            if hour is not None:
                found.hour = hour
                what.append("time")
            if weekday is not None:
                found.weekday = weekday
            if day_of_month is not None:
                found.day_of_month = day_of_month
        if paused is not None and paused != found.paused:
            found.paused = paused
            what.append("paused" if paused else "resumed")
            if not paused and found.last_outcome == Outcome.STOPPED:
                found.last_outcome = Outcome.NEVER
        found.save()
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.REPORT_SCHEDULE_CHANGED,
            entity_type="report_schedule",
            entity_id=str(found.pk),
            changes=[
                audit.FieldChange(
                    "report_schedule", str(found.pk), "changed", None, ", ".join(what)
                )
            ],
        )
    return found


def delete(*, user: User, schedule_id: int) -> None:
    with transaction.atomic():
        found = _mine(user, schedule_id)
        report = found.report
        found.delete()
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.REPORT_SCHEDULE_DELETED,
            entity_type="report_schedule",
            entity_id=str(schedule_id),
            changes=[
                audit.FieldChange("report_schedule", str(schedule_id), "report", report, None)
            ],
        )


def set_allowed_domains(*, user: User, domains: list[str]) -> list[str]:
    """The email domains reports may go to. Admin only. A domain is a bare name such as
    `example.co.za`: no address, no wildcard."""
    if user.role != Role.ADMIN:
        raise _refuse(403, "auth.forbidden", "Your role may not do this.")
    cleaned: list[str] = []
    for item in domains:
        domain = item.strip().lower()
        if not domain:
            continue
        if "@" in domain or "*" in domain or " " in domain or "." not in domain:
            raise _refuse(
                422, "report.bad_domain", f"{item!r} is not a domain such as example.co.za."
            )
        if domain not in cleaned:
            cleaned.append(domain)
    if len(cleaned) > MAX_DOMAINS:
        raise _refuse(422, "report.too_many", f"At most {MAX_DOMAINS} domains.")
    with transaction.atomic():
        row, _ = ReportSettings.objects.select_for_update(no_key=True).get_or_create(pk=1)
        before = sorted(row.allowed_domains)
        row.allowed_domains = sorted(cleaned)
        row.updated_by = user
        row.save(update_fields=["allowed_domains", "updated_by"])
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.REPORT_DOMAINS_CHANGED,
            entity_type="report_settings",
            entity_id="1",
            changes=[
                audit.FieldChange(
                    "report_settings",
                    "1",
                    "allowed_domains",
                    ", ".join(before) or None,
                    ", ".join(row.allowed_domains) or None,
                )
            ],
        )
    return list(row.allowed_domains)


# --- sending -----------------------------------------------------------------------------------


def _local(moment: datetime) -> datetime:
    return timezone.localtime(moment, ZoneInfo(settings.TIME_ZONE)).replace(tzinfo=None)


def due(schedule: ReportSchedule, now: datetime) -> bool:
    return rules.is_due(
        schedule.frequency,
        schedule.hour,
        schedule.weekday,
        schedule.day_of_month,
        now=_local(now),
        created_at=_local(schedule.created_at),
        last_sent=_local(schedule.last_sent_at) if schedule.last_sent_at else None,
    )


def send_due(now: datetime | None = None) -> int:
    """Send every schedule that is due. Returns how many went out. One schedule failing never stops
    the others."""
    now = now or timezone.now()
    sent = 0
    for schedule_id in ReportSchedule.objects.filter(paused=False).values_list("pk", flat=True):
        try:
            sent += int(send_one(schedule_id, now))
        except Exception:
            log.exception("report schedule %s could not be processed", schedule_id)
    return sent


def _outcome(
    schedule: ReportSchedule, now: datetime, outcome: str, action: str, note: str, count: int
) -> None:
    schedule.last_sent_at = now
    schedule.last_outcome = outcome
    schedule.save(update_fields=["last_sent_at", "last_outcome", "paused"])
    audit.record(  # last write of the transaction
        actor=schedule.owner,  # sent in the owner's name, by the scheduler
        actor_type=ActorType.SYSTEM,
        action=action,
        outcome=AuditOutcome.FAILED if outcome != Outcome.SENT else AuditOutcome.SUCCESS,
        entity_type="report_schedule",
        entity_id=str(schedule.pk),
        reason=note,
        changes=[
            audit.FieldChange("report_schedule", str(schedule.pk), "recipients", None, str(count))
        ],
    )


def send_one(schedule_id: int, now: datetime) -> bool:
    """Send one schedule if it is due. True when an email went out."""
    with transaction.atomic():
        schedule = (
            ReportSchedule.objects.select_for_update(skip_locked=True, no_key=True, of=("self",))
            .select_related("owner", "queue")
            .filter(pk=schedule_id, paused=False)
            .first()
        )
        if schedule is None or not due(schedule, now):
            return False
        if not schedule.owner.is_active:
            schedule.paused = True
            _outcome(schedule, now, Outcome.STOPPED, Action.REPORT_STOPPED, "owner deactivated", 0)
            return False
        allowed = set(allowed_domains())
        recipients = [r for r in schedule.recipients if _domain_of(r) in allowed]
        if not recipients:
            _outcome(
                schedule, now, Outcome.FAILED, Action.REPORT_FAILED, "no allowed recipients", 0
            )
            return False
        first, last = rules.period(schedule.frequency, _local(now).date())
        try:
            title, workbook = renderers.render(schedule, first, last)
            for address in recipients:  # one message each: nobody sees who else received it
                mail = EmailMessage(
                    subject=f"WFM report: {title} ({first:%d %b} to {last:%d %b %Y})",
                    body=(
                        f"{title} for {first:%d %B %Y} to {last:%d %B %Y}, as scheduled by its "
                        "owner. The figures are in the attached workbook."
                    ),
                    to=[address],
                )
                mail.attach(f"{schedule.report}-{last:%Y-%m-%d}.xlsx", workbook, renderers.XLSX)
                mail.send(fail_silently=False)
        except Exception:
            log.exception("report schedule %s failed", schedule.pk)
            _outcome(
                schedule, now, Outcome.FAILED, Action.REPORT_FAILED, "could not be built or sent", 0
            )
            return False
        _outcome(schedule, now, Outcome.SENT, Action.REPORT_SENT, "", len(recipients))
        return True
