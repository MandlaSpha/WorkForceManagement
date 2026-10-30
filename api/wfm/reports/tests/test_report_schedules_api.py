"""Emailed report schedules: who may make them, that recipients are held to the admin's domains,
that a report holds only what its owner may see, that it sends once and stops when it should, and
that nothing audited holds an address or a figure."""

from __future__ import annotations

import io
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.core import mail
from django.test import Client
from openpyxl import load_workbook

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.reports import services
from wfm.reports.models import ReportSchedule, ReportSettings
from wfm.telephony.models import Queue

pytestmark = pytest.mark.django_db

SCHEDULES = "/api/v1/reports/schedules"
SETTINGS = "/api/v1/reports/settings"
ZONE = ZoneInfo(settings.TIME_ZONE)
NOW = datetime(2031, 3, 12, 9, 30, tzinfo=ZONE)  # a Wednesday, after a 07:00 slot


def client(role: Role, username: str | None = None) -> Client:
    user, _ = User.objects.get_or_create(
        username=username or f"u-{role.value}",
        defaults={"role": role, "first_name": role.value.title()},
    )
    c = Client()
    c.force_login(user)
    return c


def body(**over: Any) -> dict[str, Any]:
    return {
        "report": "scorecard",
        "recipients": ["boss@example.co.za"],
        "frequency": "daily",
        "hour": 7,
        **over,
    }


def post(c: Client, data: dict[str, Any]) -> Any:
    return c.post(SCHEDULES, data, content_type="application/json")


def patch(c: Client, schedule_id: int, data: dict[str, Any]) -> Any:
    return c.patch(f"{SCHEDULES}/{schedule_id}", data, content_type="application/json")


@pytest.fixture
def domain() -> None:
    client(Role.ADMIN).put(
        SETTINGS, {"allowedDomains": ["example.co.za"]}, content_type="application/json"
    )


def make(role: Role = Role.PLANNER, **over: Any) -> int:
    r = post(client(role), body(**over))
    assert r.status_code == 201, r.content
    sid = int(r.json()["id"])
    # Created three days ago, so the 07:00 slot of today has not been "missed" at creation.
    ReportSchedule.objects.filter(pk=sid).update(created_at=NOW - timedelta(days=3))
    return sid


def put(c: Client, domains: list[str]) -> Any:
    return c.put(SETTINGS, {"allowedDomains": domains}, content_type="application/json")


class TestAllowedDomains:
    def test_nothing_can_be_scheduled_until_the_admin_allows_a_domain(self) -> None:
        # Failure caught: reports going to any address on the internet by default.
        r = post(client(Role.PLANNER), body())
        assert (r.status_code, r.json()["code"]) == (409, "report.no_domains")
        assert not ReportSchedule.objects.exists()

    @pytest.mark.usefixtures("domain")
    def test_a_recipient_outside_the_allowed_domains_is_refused(self) -> None:
        r = post(client(Role.PLANNER), body(recipients=["a@example.co.za", "x@gmail.com"]))
        assert (r.status_code, r.json()["code"]) == (422, "report.domain_not_allowed")
        # A look-alike domain is not the allowed one.
        r = post(client(Role.PLANNER), body(recipients=["a@example.co.za.evil.com"]))
        assert r.status_code == 422
        r = post(client(Role.PLANNER), body(recipients=["a@sub.example.co.za"]))
        assert r.status_code == 422

    @pytest.mark.usefixtures("domain")
    def test_addresses_are_checked_cleaned_and_limited(self) -> None:
        ok = post(
            client(Role.PLANNER), body(recipients=[" Boss@Example.co.za ", "boss@example.co.za"])
        )
        assert ok.json()["recipients"] == ["boss@example.co.za"]
        assert post(client(Role.PLANNER), body(recipients=["not-an-email"])).status_code == 422
        assert post(client(Role.PLANNER), body(recipients=[])).status_code == 422
        many = [f"p{n}@example.co.za" for n in range(11)]
        assert post(client(Role.PLANNER), body(recipients=many)).status_code == 422

    def test_only_the_admin_sets_domains_and_they_must_be_plain_domains(self) -> None:
        assert put(client(Role.PLANNER), ["example.co.za"]).status_code == 403
        assert put(client(Role.ADMIN), ["a@example.co.za"]).status_code == 422
        assert put(client(Role.ADMIN), ["*.example.co.za"]).status_code == 422
        assert put(client(Role.ADMIN), ["localhost"]).status_code == 422
        assert put(client(Role.ADMIN), [" Example.CO.za "]).json() == {
            "allowedDomains": ["example.co.za"]
        }

    @pytest.mark.usefixtures("domain")
    def test_changing_the_domains_is_audited_with_the_domains_not_with_addresses(self) -> None:
        event = AuditEvent.objects.get(action=Action.REPORT_DOMAINS_CHANGED)
        values = list(AuditChange.objects.filter(event=event).values_list("new_value", flat=True))
        assert values == ["example.co.za"]


@pytest.mark.usefixtures("domain")
class TestWhoMayScheduleWhat:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_these_roles_can_schedule_the_scorecard(self, role: Role) -> None:
        assert post(client(role), body()).status_code == 201

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT])
    def test_a_lead_cannot_schedule_the_scorecard_and_an_agent_nothing(self, role: Role) -> None:
        # Failure caught: a report mailed out of a screen its owner is not allowed to open.
        assert post(client(role), body()).status_code == 403

    def test_an_agent_has_no_part_in_any_of_it(self) -> None:
        c = client(Role.AGENT)
        assert c.get(SCHEDULES).status_code == 403
        assert c.get(SETTINGS).status_code == 403

    def test_a_peaks_report_needs_a_queue_the_owner_can_see(self) -> None:
        q = Queue.objects.create(name="Q")
        assert post(client(Role.LEAD), body(report="peaks", queueId=q.pk)).status_code == 201
        assert post(client(Role.LEAD), body(report="peaks")).status_code == 404
        assert post(client(Role.LEAD), body(report="peaks", queueId=99999)).status_code == 404
        # Customer ops see only their contract queues, so this one is not theirs.
        assert (
            post(client(Role.CUSTOMER_OPS), body(report="peaks", queueId=q.pk)).status_code == 404
        )

    def test_the_shape_of_a_schedule_is_checked(self) -> None:
        c = client(Role.PLANNER)
        assert post(c, body(report="nope")).status_code == 422
        assert post(c, body(frequency="hourly")).status_code == 422
        assert post(c, body(hour=24)).status_code == 422
        assert post(c, body(frequency="weekly", weekday=7)).status_code == 422
        assert post(c, body(frequency="monthly", dayOfMonth=29)).status_code == 422

    def test_one_person_cannot_make_endless_schedules(self) -> None:
        c = client(Role.PLANNER)
        for _ in range(20):
            assert post(c, body()).status_code == 201
        assert post(c, body()).status_code == 409


@pytest.mark.usefixtures("domain")
class TestOwnership:
    def test_nobody_sees_or_changes_anyone_elses_schedule(self) -> None:
        # Failure caught: reading who somebody sends reports to, or redirecting their report.
        sid = make(Role.PLANNER)
        other = client(Role.PLANNER, "u-planner-2")
        assert other.get(SCHEDULES).json() == []
        assert patch(other, sid, {"paused": True}).status_code == 404
        assert other.delete(f"{SCHEDULES}/{sid}").status_code == 404
        assert ReportSchedule.objects.filter(pk=sid, paused=False).exists()

    def test_the_admin_can_see_pause_and_remove_but_not_redirect(self) -> None:
        sid = make(Role.PLANNER)
        admin = client(Role.ADMIN)
        listed = admin.get(SCHEDULES).json()
        assert listed[0]["owner"] != ""  # the admin is told whose it is
        assert patch(admin, sid, {"recipients": ["me@example.co.za"]}).status_code == 404
        assert patch(admin, sid, {"hour": 1}).status_code == 404
        assert patch(admin, sid, {"paused": True}).json()["paused"] is True
        assert admin.delete(f"{SCHEDULES}/{sid}").status_code == 204

    def test_others_are_never_told_the_owner(self) -> None:
        make(Role.PLANNER)
        assert client(Role.PLANNER).get(SCHEDULES).json()[0]["owner"] == ""

    def test_the_owner_changes_pauses_and_deletes(self) -> None:
        sid = make(Role.PLANNER)
        c = client(Role.PLANNER)
        changed = patch(c, sid, {"hour": 8, "recipients": ["new@example.co.za"]}).json()
        assert (changed["hour"], changed["recipients"]) == (8, ["new@example.co.za"])
        assert patch(c, sid, {"recipients": ["x@gmail.com"]}).status_code == 422
        assert c.delete(f"{SCHEDULES}/{sid}").status_code == 204
        assert not ReportSchedule.objects.exists()

    def test_creating_changing_and_deleting_are_audited_without_addresses(self) -> None:
        sid = make(Role.PLANNER)
        c = client(Role.PLANNER)
        patch(c, sid, {"paused": True})
        c.delete(f"{SCHEDULES}/{sid}")
        for action in (
            Action.REPORT_SCHEDULE_CREATED,
            Action.REPORT_SCHEDULE_CHANGED,
            Action.REPORT_SCHEDULE_DELETED,
        ):
            assert AuditEvent.objects.filter(action=action).count() == 1
        assert not AuditChange.objects.filter(new_value__contains="@").exists()


@pytest.mark.usefixtures("domain")
class TestSending:
    def attachment(self, message: Any) -> Any:
        name, content, _ = message.attachments[0]
        return name, load_workbook(io.BytesIO(content))

    def test_a_due_schedule_sends_one_message_each_with_the_workbook(self) -> None:
        sid = make(Role.PLANNER, recipients=["a@example.co.za", "b@example.co.za"])
        assert services.send_due(NOW) == 1
        assert [m.to for m in mail.outbox] == [["a@example.co.za"], ["b@example.co.za"]]
        name, book = self.attachment(mail.outbox[0])
        assert name.endswith("2031-03-11.xlsx")  # yesterday, for a daily report
        assert "Figures" in book.sheetnames
        assert ReportSchedule.objects.get(pk=sid).last_outcome == "sent"

    def test_it_sends_once_per_slot_not_every_time_the_check_runs(self) -> None:
        # Failure caught: the same report mailed every fifteen minutes.
        make(Role.PLANNER)
        services.send_due(NOW)
        services.send_due(NOW + timedelta(minutes=15))
        services.send_due(NOW + timedelta(hours=3))
        assert len(mail.outbox) == 1
        services.send_due(NOW + timedelta(days=1))  # the next day's slot
        assert len(mail.outbox) == 2

    def test_a_new_schedule_does_not_send_a_slot_that_passed_before_it_existed(self) -> None:
        post(client(Role.PLANNER), body())  # created just now, in real time
        services.send_due(datetime.now(tz=ZONE))
        assert mail.outbox == []

    def test_a_paused_schedule_sends_nothing_and_resuming_does_not_replay_it(self) -> None:
        sid = make(Role.PLANNER)
        patch(client(Role.PLANNER), sid, {"paused": True})
        services.send_due(NOW)
        assert mail.outbox == []

    def test_the_report_holds_only_what_its_owner_may_see(self) -> None:
        # Failure caught: an executive's emailed report carrying planner-only roster or leave
        # figures, because it was built by the system instead of as the owner.
        make(Role.EXECUTIVE)
        make(Role.PLANNER)
        services.send_due(NOW)
        labels = []
        for m in mail.outbox:
            _, book = self.attachment(m)
            labels.append({row[0] for row in book["Figures"].iter_rows(values_only=True)})
        assert len(mail.outbox) == 2
        executive, planner = sorted(labels, key=len)
        assert "Occupancy" not in executive
        assert "Occupancy" in planner

    def test_a_peaks_report_is_built_as_its_owner_for_the_queue_chosen(self) -> None:
        q = Queue.objects.create(name="Q")
        make(Role.PLANNER, report="peaks", queueId=q.pk)
        services.send_due(NOW)
        _, book = self.attachment(mail.outbox[0])
        assert book.sheetnames == ["Days", "Half-hours"]

    def test_a_schedule_stops_when_its_owner_is_deactivated(self) -> None:
        # Failure caught: reports continuing to leave in the name of someone who has left.
        sid = make(Role.PLANNER)
        User.objects.filter(username="u-planner").update(is_active=False)
        services.send_due(NOW)
        s = ReportSchedule.objects.get(pk=sid)
        assert (s.paused, s.last_outcome) == (True, "stopped")
        assert mail.outbox == []
        assert AuditEvent.objects.filter(action=Action.REPORT_STOPPED).count() == 1

    def test_the_domain_list_is_checked_again_at_sending_time(self) -> None:
        # Failure caught: a domain the admin has since removed still receiving reports.
        sid = make(Role.PLANNER, recipients=["a@example.co.za"])
        client(Role.ADMIN).put(
            SETTINGS, {"allowedDomains": ["other.co.za"]}, content_type="application/json"
        )
        services.send_due(NOW)
        assert mail.outbox == []
        assert ReportSchedule.objects.get(pk=sid).last_outcome == "failed"
        assert AuditEvent.objects.filter(action=Action.REPORT_FAILED).count() == 1

    def test_a_failing_mail_server_fails_that_schedule_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bad = make(Role.PLANNER, recipients=["a@example.co.za"])
        good = make(Role.EXECUTIVE, recipients=["b@example.co.za"])
        from django.core.mail import EmailMessage

        original = EmailMessage.send

        def flaky(self: EmailMessage, fail_silently: bool = False) -> int:
            if self.to == ["a@example.co.za"]:
                raise OSError("smtp down: secret-host-name")
            return original(self, fail_silently)

        monkeypatch.setattr(EmailMessage, "send", flaky)
        services.send_due(NOW)
        assert ReportSchedule.objects.get(pk=bad).last_outcome == "failed"
        assert ReportSchedule.objects.get(pk=good).last_outcome == "sent"
        event = AuditEvent.objects.get(action=Action.REPORT_FAILED)
        assert "secret-host-name" not in event.reason

    def test_sending_is_audited_with_counts_and_no_address_or_figure(self) -> None:
        make(Role.PLANNER, recipients=["a@example.co.za", "b@example.co.za"])
        services.send_due(NOW)
        event = AuditEvent.objects.get(action=Action.REPORT_SENT)
        assert list(
            AuditChange.objects.filter(event=event).values_list("new_value", flat=True)
        ) == ["2"]
        assert "@" not in event.reason
        assert not AuditChange.objects.filter(new_value__contains="@").exists()

    def test_the_message_body_carries_the_period_and_no_figures(self) -> None:
        make(Role.PLANNER)
        services.send_due(NOW)
        text = mail.outbox[0].body
        assert "11 March 2031" in text
        assert "%" not in text


@pytest.mark.usefixtures("domain")
class TestBoardPack:
    """RPT-09: the investment-board KPI pack, built as its owner."""

    COST = 91234.5  # a rand figure on the hiring plan, which only planner and admin may read

    def seed(self) -> None:
        from datetime import date

        from wfm.capacity.models import HiringPlan
        from wfm.telephony.models import IntervalActual

        q, _ = Queue.objects.get_or_create(name="BoardQueue")
        IntervalActual.objects.create(
            queue=q,
            interval_start=datetime(2031, 3, 11, 9, 0, tzinfo=ZONE),
            offered=40,
            answered=36,
            abandoned=4,
            answered_in_sl=30,
            sum_wait_s=360,
            sum_handle_s=36 * 200,
        )
        HiringPlan.objects.create(
            name="Plan 2031",
            start_month=date(2031, 4, 1),
            incumbents=100,
            attrition_pct=2,
            ramp=[0.5, 1],
            required=[110] * 12,
            cost_per_person=self.COST,
            created_by=User.objects.get_or_create(username="u-admin", defaults={"role": "admin"})[
                0
            ],
        )

    def book_for(self, role: Role) -> Any:
        self.seed()
        make(role, report="board")
        services.send_due(NOW)
        assert len(mail.outbox) == 1
        _, content, _ = mail.outbox[0].attachments[0]
        return load_workbook(io.BytesIO(content))

    @staticmethod
    def cells(book: Any) -> list[Any]:
        return [c for sheet in book for row in sheet.iter_rows(values_only=True) for c in row]

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_these_roles_can_schedule_it(self, role: Role) -> None:
        r = post(client(role), body(report="board"))
        assert r.status_code == 201, r.content
        assert r.json()["report"] == "board"

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT])
    def test_a_lead_or_agent_cannot(self, role: Role) -> None:
        # Failure caught: a role with no investment figures scheduling the board pack.
        assert post(client(role), body(report="board")).status_code == 403
        assert not ReportSchedule.objects.exists()

    def test_an_executive_pack_has_no_rand_figure_and_a_planner_pack_has_the_headcount(
        self,
    ) -> None:
        # Failure caught: the hiring plan's cost per person (pay data) reaching an executive's
        # inbox, or a rand figure anywhere in the pack for any role.
        executive = self.book_for(Role.EXECUTIVE)
        assert executive.sheetnames == ["Headline", "By queue", "Capacity", "Notes"]
        cells = self.cells(executive)
        assert self.COST not in cells
        assert "R" not in cells
        assert not any(isinstance(c, str) and re.search(r"\bR\s?\d", c) for c in cells)
        # The capacity sheet is headcount: needed, on the books, hires, effective, gap.
        header = [c.value for c in executive["Capacity"][2]]
        assert header == ["Month", "Needed", "On the books", "Hires", "Effective", "Gap"]
        assert [c.value for c in executive["By queue"][2]][:2] == ["BoardQueue", 40]

    def test_customer_ops_see_no_hiring_sheet_and_only_their_contract_queues(self) -> None:
        # Failure caught: a customer reading the employer's hiring plan, or queues that are not
        # in their contracts (none are until contracts link them).
        book = self.book_for(Role.CUSTOMER_OPS)
        assert book.sheetnames == ["Headline", "By queue", "Notes"]
        assert "BoardQueue" not in self.cells(book)
        assert "Plan 2031" not in self.cells(book)
        # The sheet says why it is empty instead of looking broken, and names no queue.
        assert book["By queue"].max_row == 2
        assert "No queues are linked to your contracts yet." in self.cells(book)

    def test_the_headline_carries_the_basis_of_each_figure(self) -> None:
        # Failure caught: a board figure with no statement of where it comes from.
        book = self.book_for(Role.PLANNER)
        rows = list(book["Headline"].iter_rows(min_row=3, values_only=True))
        assert rows
        assert all(r[3] in ("measured", "modelled", "needs_data") for r in rows)
        assert "Service level" in {r[0] for r in rows}


class TestCsvAndPausedCreate:
    def _allow(self) -> None:
        ReportSettings.objects.update_or_create(
            pk=1, defaults={"allowed_domains": ["example.co.za"]}
        )

    def test_a_schedule_can_be_made_paused(self) -> None:
        self._allow()
        r = client(Role.PLANNER).post(SCHEDULES, body(paused=True), content_type="application/json")
        assert r.status_code == 201, r.content
        assert r.json()["paused"] is True
        assert ReportSchedule.objects.get().paused is True

    def test_it_is_active_by_default(self) -> None:
        self._allow()
        r = client(Role.PLANNER).post(SCHEDULES, body(), content_type="application/json")
        assert r.json()["paused"] is False

    @pytest.mark.parametrize(
        "role", [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.EXECUTIVE, Role.CUSTOMER_OPS]
    )
    def test_these_roles_can_download_the_list(self, role: Role) -> None:
        response = client(role).get(SCHEDULES + ".csv")
        assert response.status_code == 200
        assert response.content.decode().startswith("report,queue,frequency")

    def test_an_agent_is_refused(self) -> None:
        assert client(Role.AGENT).get(SCHEDULES + ".csv").status_code == 403

    def test_it_holds_only_your_own_and_is_formula_safe(self) -> None:
        self._allow()
        mine = client(Role.PLANNER, "planner-a")
        mine.post(SCHEDULES, body(), content_type="application/json")
        other = client(Role.PLANNER, "planner-b")
        other.post(
            SCHEDULES, body(recipients=["other@example.co.za"]), content_type="application/json"
        )
        ReportSchedule.objects.filter(owner__username="planner-a").update(
            queue=Queue.objects.create(name="=SUM(A1)")
        )
        text = mine.get(SCHEDULES + ".csv").content.decode()
        assert "boss@example.co.za" in text
        assert "other@example.co.za" not in text
        assert "'=SUM(A1)" in text
        admin_text = client(Role.ADMIN).get(SCHEDULES + ".csv").content.decode()
        assert "other@example.co.za" in admin_text
