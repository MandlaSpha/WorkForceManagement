"""The purge command deletes data, so the tests are about what it must NEVER delete."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.core.management import CommandError, call_command

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent
from wfm.telephony import services
from wfm.telephony.models import CallRecord, ImportBatch, IntervalActual, Queue
from wfm.telephony.tests.workbooks import Call, workbook_bytes

pytestmark = pytest.mark.django_db


def import_calls(calls: list[Call]) -> ImportBatch:
    user, _ = User.objects.get_or_create(username="importer", defaults={"role": Role.PLANNER})
    return services.import_cdr(user=user, file_name="x.xlsx", content=workbook_bytes(calls))


def call(call_id: int, queue: str) -> Call:
    return Call(call_id, queue, "Agent", "2026-05-04 09:00:00", wait=1, talk=10)


@pytest.fixture
def development(settings: Any) -> None:
    settings.DEBUG = True


def test_refuses_outside_development(settings: Any) -> None:
    settings.DEBUG = False
    import_calls([call(1, "E2E Queue")])

    with pytest.raises(CommandError, match="development only"):
        call_command("purge_e2e_data")

    assert CallRecord.objects.count() == 1


@pytest.mark.usefixtures("development")
def test_removes_the_test_queue_and_its_imports() -> None:
    import_calls([call(1, "E2E Queue"), call(2, "E2E Queue")])

    call_command("purge_e2e_data")

    assert (CallRecord.objects.count(), IntervalActual.objects.count()) == (0, 0)
    assert (ImportBatch.objects.count(), Queue.objects.count()) == (0, 0)


@pytest.mark.usefixtures("development")
def test_never_touches_real_queues_or_their_imports() -> None:
    import_calls([call(1, "E2E Queue")])
    real = import_calls([call(2, "TotalSA"), call(3, "Platinumhealth")])

    call_command("purge_e2e_data")

    assert set(Queue.objects.values_list("name", flat=True)) == {"TotalSA", "Platinumhealth"}
    assert CallRecord.objects.count() == 2
    assert IntervalActual.objects.count() == 2
    assert list(ImportBatch.objects.values_list("pk", flat=True)) == [real.pk]


@pytest.mark.usefixtures("development")
def test_keeps_an_import_that_mixes_test_and_real_calls() -> None:
    # If a real file ever contained a call in the test queue, the file and its other calls stay.
    mixed = import_calls([call(1, "E2E Queue"), call(2, "TotalSA")])

    call_command("purge_e2e_data")

    assert ImportBatch.objects.filter(pk=mixed.pk).exists()
    assert CallRecord.objects.filter(queue__name="TotalSA").count() == 1


@pytest.mark.usefixtures("development")
def test_says_what_it_deleted_in_the_audit_trail() -> None:
    import_calls([call(1, "E2E Queue")])

    call_command("purge_e2e_data")

    event = AuditEvent.objects.get(action=Action.DEV_DATA_PURGED)
    assert event.reason == "1 calls, 1 imports, 0 forecasts"


@pytest.mark.usefixtures("development")
def test_is_a_no_op_when_there_is_nothing_to_purge() -> None:
    import_calls([call(1, "TotalSA")])

    call_command("purge_e2e_data")

    assert CallRecord.objects.count() == 1
    assert not AuditEvent.objects.filter(action=Action.DEV_DATA_PURGED).exists()


@pytest.mark.usefixtures("development")
def test_removes_the_forecasts_of_the_test_queue_and_keeps_everyone_elses() -> None:
    from wfm.forecasting import services as forecasting
    from wfm.forecasting.models import ForecastInterval, ForecastVersion

    user = User.objects.create_user(username="planner", password="x", role=Role.PLANNER)
    for day in ("2026-05-04", "2026-05-11"):  # one file per day, holding both queues
        number = int(day[-2:])
        import_calls(
            [
                Call(number, "E2E Queue", "Agent", f"{day} 09:00:00", wait=1, talk=10),
                Call(number + 100, "TotalSA", "Agent", f"{day} 09:00:00", wait=1, talk=10),
            ]
        )
    for queue in ("E2E Queue", "TotalSA"):
        forecasting.run_forecast(
            user=user,
            queue_id=Queue.objects.get(name=queue).pk,
            date_from=date(2026, 5, 18),
            date_to=date(2026, 5, 18),
        )
    assert ForecastVersion.objects.count() == 2

    call_command("purge_e2e_data")

    remaining = ForecastVersion.objects.get()
    assert remaining.queue.name == "TotalSA"
    assert ForecastInterval.objects.filter(version=remaining).count() == 48
    assert ForecastInterval.objects.exclude(version=remaining).count() == 0


@pytest.mark.usefixtures("development")
def test_removes_every_queue_with_the_test_prefix_and_only_those() -> None:
    import_calls([call(1, "E2E Queue"), call(2, "E2E Queue abc123"), call(3, "TotalSA")])

    call_command("purge_e2e_data")

    assert list(Queue.objects.values_list("name", flat=True)) == ["TotalSA"]


@pytest.mark.usefixtures("development")
@pytest.mark.parametrize("prefix", ["", "  ", "E2"])
def test_refuses_a_prefix_short_enough_to_catch_real_queues(prefix: str) -> None:
    import_calls([call(1, "E2E Queue")])
    with pytest.raises(CommandError, match="too short"):
        call_command("purge_e2e_data", prefix=prefix)
    assert Queue.objects.count() == 1


@pytest.mark.usefixtures("development")
def test_removes_the_skills_and_rosters_of_a_test_queue_and_keeps_a_real_one() -> None:
    # Failure caught: the purge stopping on "protected" skills and roster weeks of a test queue
    # (the dev database filled with hundreds of test queues), or deleting a real queue's.
    from wfm.scheduling.models import Employee, EmployeeSkill, RosterWeek

    test_queue = Queue.objects.create(name="E2E Queue skills")
    real_queue = Queue.objects.create(name="Billing")
    person = Employee.objects.create(emp_no="E-1", name="Test Person")
    for queue in (test_queue, real_queue):
        EmployeeSkill.objects.create(employee=person, queue=queue)
        RosterWeek.objects.create(queue=queue, week_start=date(2026, 10, 19))

    call_command("purge_e2e_data")

    assert list(Queue.objects.values_list("name", flat=True)) == ["Billing"]
    assert EmployeeSkill.objects.filter(queue=real_queue).count() == 1
    assert RosterWeek.objects.filter(queue=real_queue).count() == 1
    assert not EmployeeSkill.objects.filter(queue__name__startswith="E2E").exists()
