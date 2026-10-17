"""Background jobs: who may start one and read it, that it runs as its owner through the same rules,
that a double click does not do the work twice, and that a failure leaks nothing."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent
from wfm.jobs import services
from wfm.jobs.models import Job, JobStatus
from wfm.jobs.registry import RUNNERS
from wfm.scheduling.models import RosterStatus, RosterWeek, ShiftAssignment
from wfm.scheduling.tests.helpers import (
    MON,
    login,
    person,
    publish_forecast,
    queue,
    standard_shifts,
)
from wfm.telephony.models import Queue

pytestmark = pytest.mark.django_db

START = "/api/v1/scheduling/roster/auto-schedule/jobs"
FORECAST_START = "/api/v1/forecasting/versions/jobs"
Capture = Callable[..., Any]


@pytest.fixture(autouse=True)
def shifts() -> dict[str, Any]:
    return standard_shifts()


def need() -> dict[tuple[Any, int], int | None]:
    return {(MON, slot): 1 for slot in range(18, 35)}


def start(client: Client, q: Any = None) -> Any:
    body = {"queueId": (q or queue()).pk, "weekStart": str(MON)}
    return client.post(START, body, content_type="application/json")


def run_started(client: Client, capture: Capture, q: Any = None) -> Any:
    """Start a job and let the worker (eager in tests) do it once the request has committed."""
    with capture(execute=True):
        response = start(client, q)
    assert response.status_code == 202, response.content
    return response.json()


class TestStarting:
    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN])
    def test_planner_and_admin_can_start_one(
        self, role: Role, django_capture_on_commit_callbacks: Capture
    ) -> None:
        person()
        publish_forecast(queue(), need())
        job = run_started(login(role), django_capture_on_commit_callbacks)
        assert job["kind"] == "auto_schedule"

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_the_same_roles_refused_a_click_are_refused_a_job(self, role: Role) -> None:
        # Failure caught: the background route being a way round the roster permissions.
        person()
        publish_forecast(queue(), need())
        assert start(login(role)).status_code == 403
        assert Job.objects.count() == 0
        assert ShiftAssignment.objects.count() == 0

    def test_an_unknown_queue_is_not_found_and_nothing_is_queued(self) -> None:
        body = {"queueId": 999999, "weekStart": str(MON)}
        r = login().post(START, body, content_type="application/json")
        assert r.status_code == 404
        assert Job.objects.count() == 0

    def test_a_double_click_is_one_job(self) -> None:
        # Failure caught: two workers filling the same week at once.
        person()
        publish_forecast(queue(), need())
        first = start(login()).json()
        second = start(login()).json()
        assert first["id"] == second["id"]
        assert Job.objects.count() == 1

    def test_asking_again_after_it_finished_is_a_new_job(
        self, django_capture_on_commit_callbacks: Capture
    ) -> None:
        person()
        publish_forecast(queue(), need())
        first = run_started(login(), django_capture_on_commit_callbacks)
        second = run_started(login(), django_capture_on_commit_callbacks)
        assert first["id"] != second["id"]


class TestRunning:
    def test_it_does_what_the_click_does_and_reports_counts_only(
        self, django_capture_on_commit_callbacks: Capture
    ) -> None:
        e1 = person()
        publish_forecast(queue(), need())
        started = run_started(login(), django_capture_on_commit_callbacks)
        job = login().get(f"/api/v1/jobs/{started['id']}").json()
        assert job["status"] == "done"
        assert (job["result"]["placed"], job["result"]["shortAfter"]) == (1, 0)
        assert ShiftAssignment.objects.get().employee_id == e1.pk
        assert "Person" not in str(job)  # no name in a job
        # The change is in the audit trail, by the person who asked, not by "the system".
        event = AuditEvent.objects.get(action=Action.ROSTER_AUTO_SCHEDULED)
        assert event.actor_user_id == User.objects.get(username="u-planner").pk

    def test_the_roster_rules_still_apply(
        self, django_capture_on_commit_callbacks: Capture
    ) -> None:
        # Failure caught: a worker writing shifts the roster would refuse (a published week).
        person()
        q = queue()
        publish_forecast(q, need())
        RosterWeek.objects.create(queue=q, week_start=MON, status=RosterStatus.PUBLISHED)
        started = run_started(login(), django_capture_on_commit_callbacks, q)
        job = login().get(f"/api/v1/jobs/{started['id']}").json()
        assert (job["status"], job["errorCode"]) == ("failed", "autoschedule.published")
        assert ShiftAssignment.objects.count() == 0

    def test_an_unexpected_failure_says_nothing_about_why(
        self, django_capture_on_commit_callbacks: Capture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Failure caught: an internal error (a path, a query, a value) shown to the screen.
        def boom(user: User, params: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("secret internal detail 12345")

        monkeypatch.setitem(RUNNERS, "auto_schedule", boom)
        person()
        publish_forecast(queue(), need())
        started = run_started(login(), django_capture_on_commit_callbacks)
        job = login().get(f"/api/v1/jobs/{started['id']}").json()
        assert (job["status"], job["errorCode"]) == ("failed", "job.failed")
        assert "secret" not in str(job)
        assert "12345" not in str(job)

    def test_a_deactivated_owner_s_job_does_not_run(self) -> None:
        # Failure caught: work carrying on in the name of someone who has left.
        person()
        publish_forecast(queue(), need())
        user = User.objects.get_or_create(username="u-planner", defaults={"role": Role.PLANNER})[0]
        job = Job.objects.create(owner=user, kind="auto_schedule", params={})
        user.is_active = False
        user.save()
        services.run(str(job.pk))
        job.refresh_from_db()
        assert (job.status, job.error_code) == (JobStatus.FAILED, "job.owner_inactive")
        assert ShiftAssignment.objects.count() == 0

    def test_a_job_that_is_running_is_not_taken_twice_until_it_is_stale(self) -> None:
        # Failure caught: a redelivered message doing the work a second time while a worker is
        # still at it; and a dead worker leaving the job stuck for ever.
        user = User.objects.get_or_create(username="u-planner", defaults={"role": Role.PLANNER})[0]
        calls: list[int] = []

        def work(u: User, p: dict[str, Any]) -> dict[str, Any]:
            calls.append(1)
            return {}

        RUNNERS["test_kind"] = work
        try:
            job = Job.objects.create(
                owner=user,
                kind="test_kind",
                status=JobStatus.RUNNING,
                started_at=timezone.now() - timedelta(minutes=1),
            )
            services.run(str(job.pk))
            assert calls == []
            Job.objects.filter(pk=job.pk).update(
                started_at=timezone.now() - services.STALE_AFTER - timedelta(minutes=1)
            )
            services.run(str(job.pk))
            assert calls == [1]
            services.run(str(job.pk))  # done now: never again
            assert calls == [1]
        finally:
            del RUNNERS["test_kind"]


class TestReading:
    def test_only_the_owner_can_read_a_job_even_an_admin(
        self, django_capture_on_commit_callbacks: Capture
    ) -> None:
        # Failure caught: reading somebody else's job (and what they were doing).
        person()
        publish_forecast(queue(), need())
        started = run_started(login(Role.PLANNER), django_capture_on_commit_callbacks)
        url = f"/api/v1/jobs/{started['id']}"
        assert login(Role.PLANNER).get(url).status_code == 200
        for role in (Role.ADMIN, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS):
            assert login(role).get(url).status_code == 404

    def test_a_bad_id_is_not_found_and_signed_out_is_refused(self) -> None:
        assert login().get("/api/v1/jobs/not-a-uuid").status_code == 404
        assert Client().get("/api/v1/jobs/00000000-0000-0000-0000-000000000000").status_code in (
            401,
            403,
        )


class TestForecastJob:
    def test_roles_and_scope_match_the_forecast_itself(self) -> None:
        q = queue()
        body = {"queueId": q.pk, "dateFrom": str(MON), "dateTo": str(MON + timedelta(days=1))}

        def post(client: Client, payload: dict[str, Any]) -> Any:
            return client.post(FORECAST_START, payload, content_type="application/json")

        assert post(login(Role.AGENT), body).status_code == 403
        assert post(login(Role.EXECUTIVE), body).status_code == 403
        assert post(login(Role.PLANNER), {**body, "queueId": 999999}).status_code == 404
        assert Job.objects.count() == 0

    def test_a_forecast_runs_in_the_background_and_leaves_a_draft(
        self, django_capture_on_commit_callbacks: Capture
    ) -> None:
        # Failure caught: a finished forecast whose result cannot be stored, leaving the job
        # "running" for ever (the version id is a UUID).
        from wfm.forecasting.models import ForecastVersion
        from wfm.forecasting.tests.helpers import MON_4, MON_11, MON_18, MON_25, import_mondays

        import_mondays({MON_4: 40, MON_11: 20, MON_18: 10})
        q = Queue.objects.get(name="QueueA")
        body = {"queueId": q.pk, "dateFrom": str(MON_25), "dateTo": str(MON_25)}
        with django_capture_on_commit_callbacks(execute=True):
            r = login().post(FORECAST_START, body, content_type="application/json")
        assert r.status_code == 202
        job = login().get(f"/api/v1/jobs/{r.json()['id']}").json()
        assert job["status"] == "done", job
        version = ForecastVersion.objects.get(pk=job["result"]["versionId"])
        assert (version.queue_id, version.status) == (q.pk, "draft")

    def test_a_result_that_cannot_be_stored_fails_the_job_instead_of_sticking(
        self, django_capture_on_commit_callbacks: Capture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import uuid

        monkeypatch.setitem(RUNNERS, "auto_schedule", lambda u, p: {"id": uuid.uuid4()})
        person()
        publish_forecast(queue(), need())
        started = run_started(login(), django_capture_on_commit_callbacks)
        job = login().get(f"/api/v1/jobs/{started['id']}").json()
        assert (job["status"], job["errorCode"]) == ("failed", "job.failed")


def test_old_finished_jobs_go_and_active_ones_stay() -> None:
    user = User.objects.get_or_create(username="u-planner", defaults={"role": Role.PLANNER})[0]
    old = timezone.now() - services.KEEP_FOR - timedelta(days=1)
    gone = Job.objects.create(owner=user, kind="x", status=JobStatus.DONE)
    stuck = Job.objects.create(owner=user, kind="x", status=JobStatus.RUNNING)
    Job.objects.filter(pk__in=[gone.pk, stuck.pk]).update(created_at=old)
    assert services.delete_old() == 1
    assert list(Job.objects.values_list("pk", flat=True)) == [stuck.pk]
