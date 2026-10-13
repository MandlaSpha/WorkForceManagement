"""Ways the import could be broken or bypassed, and the guards that stop them.

Each test here names an attack or a failure and fails if the guard is removed:
cross-site upload, half-finished imports, data without its audit event, a hostile spreadsheet,
a double-clicked Upload, the database rules behind the dedupe, and rules that are too strict.
"""

from __future__ import annotations

import hashlib
import zipfile
from io import BytesIO
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit import services as audit_services
from wfm.audit.models import Action, AuditEvent
from wfm.core.errors import ApiError
from wfm.telephony import intervals, services
from wfm.telephony.models import CallRecord, ImportBatch, IntervalActual, Queue

from .workbooks import Call, scenario, upload, workbook_bytes

pytestmark = pytest.mark.django_db

IMPORTS = "/api/v1/telephony/imports"


def user_with(role: Role) -> User:
    return User.objects.create_user(username=f"u-{role.value}", password="x", role=role)


def signed_in(role: Role = Role.PLANNER, *, enforce_csrf: bool = False) -> Client:
    client = Client(enforce_csrf_checks=enforce_csrf)
    client.force_login(user_with(role))
    return client


def nothing_was_stored() -> None:
    assert ImportBatch.objects.count() == 0
    assert CallRecord.objects.count() == 0
    assert IntervalActual.objects.count() == 0
    assert Queue.objects.count() == 0
    assert AuditEvent.objects.filter(action=Action.CDR_IMPORTED).count() == 0


class TestCrossSiteUpload:
    """The session cookie is sent by the browser on any request to this site, so without a CSRF
    check another website could make a signed-in planner's browser upload a file."""

    def test_an_upload_without_the_csrf_token_is_refused_and_stores_nothing(self) -> None:
        client = signed_in(enforce_csrf=True)
        response = client.post(IMPORTS, {"file": upload(workbook_bytes(scenario()))})
        assert response.status_code == 403
        nothing_was_stored()

    def test_the_same_upload_with_the_token_goes_through(self) -> None:
        client = signed_in(enforce_csrf=True)
        token = client.get("/api/v1/auth/csrf").json()["csrfToken"]
        response = client.post(
            IMPORTS,
            {"file": upload(workbook_bytes(scenario()))},
            headers={"X-CSRFToken": token},
        )
        assert response.status_code == 201


class TestRolesWithARealFile:
    """The contract matrix proves the 403 with an empty body. This proves the refusal happens
    before anything is read or written, even when the upload is a perfectly good file."""

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_a_role_that_may_not_import_cannot_with_a_valid_file(self, role: Role) -> None:
        response = signed_in(role).post(IMPORTS, {"file": upload(workbook_bytes(scenario()))})
        assert response.status_code == 403
        nothing_was_stored()


class TestAHalfFinishedImportLeavesNothing:
    def test_a_failure_while_building_intervals_rolls_everything_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def explode(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("database went away")

        monkeypatch.setattr(intervals, "rebuild", explode)
        with pytest.raises(RuntimeError):
            services.import_cdr(
                user=user_with(Role.PLANNER), file_name="x.xlsx", content=workbook_bytes(scenario())
            )
        nothing_was_stored()

    def test_data_can_never_exist_without_its_audit_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # AUD-08: if the audit event cannot be written, the import must not happen either.
        def refuse(**kwargs: Any) -> None:
            raise RuntimeError("audit store unavailable")

        monkeypatch.setattr(audit_services, "record", refuse)
        with pytest.raises(RuntimeError):
            services.import_cdr(
                user=user_with(Role.PLANNER), file_name="x.xlsx", content=workbook_bytes(scenario())
            )
        nothing_was_stored()

    def test_the_audit_event_is_the_last_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Hard rule: the audit insert holds the chain lock until commit, so it must come after
        # the slow work. When it is called, the data and the reconciliation already exist.
        seen: list[dict[str, Any]] = []
        real = audit_services.record

        def spy(**kwargs: Any) -> Any:
            batch = ImportBatch.objects.get()
            seen.append(
                {
                    "calls": CallRecord.objects.count(),
                    "intervals": IntervalActual.objects.count(),
                    "reconciled": batch.reconciliation.get("matches") is True,
                }
            )
            return real(**kwargs)

        monkeypatch.setattr(audit_services, "record", spy)
        services.import_cdr(
            user=user_with(Role.PLANNER), file_name="x.xlsx", content=workbook_bytes(scenario())
        )
        assert seen == [{"calls": 12, "intervals": 3, "reconciled": True}]


class TestAHostileSpreadsheet:
    """The upload is untrusted XML. An XML bomb or an external entity must be refused, not
    expanded. This fails if defusedxml is removed or its protection is switched off."""

    @staticmethod
    def with_doctype(entities: str) -> bytes:
        source = zipfile.ZipFile(BytesIO(workbook_bytes(scenario())))
        out = BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename == "xl/workbook.xml":
                    doctype = f"<!DOCTYPE workbook [{entities}]>".encode()
                    data = data.replace(b"<workbook", doctype + b"<workbook", 1)
                target.writestr(item, data)
        return out.getvalue()

    @pytest.mark.parametrize(
        "entities",
        [
            '<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">',
            '<!ENTITY xxe SYSTEM "file:///etc/hosts">',
        ],
        ids=["entity-expansion", "external-entity"],
    )
    def test_is_refused_and_audited(self, entities: str) -> None:
        with pytest.raises(ApiError) as caught:
            services.import_cdr(
                user=user_with(Role.PLANNER),
                file_name="x.xlsx",
                content=self.with_doctype(entities),
            )
        assert caught.value.code == "import.not_a_workbook"
        nothing_was_stored()
        assert AuditEvent.objects.filter(action=Action.CDR_IMPORT_REFUSED).count() == 1


class TestADoubleClickedUpload:
    def test_the_slower_of_two_simultaneous_uploads_gets_a_clear_conflict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = user_with(Role.PLANNER)
        content = workbook_bytes(scenario())
        stale = services._plan(hashlib.sha256(content).hexdigest(), content)
        services.import_cdr(user=user, file_name="x.xlsx", content=content)  # the winner

        # The loser was planned before the winner finished, so it believes the file is new.
        monkeypatch.setattr(services, "_plan", lambda digest, content: stale)
        with pytest.raises(ApiError) as caught:
            services.import_cdr(user=user, file_name="x.xlsx", content=content)

        assert (caught.value.status, caught.value.code) == (409, "import.conflict")
        assert CallRecord.objects.count() == 12  # not 24
        assert ImportBatch.objects.count() == 1
        refusal = AuditEvent.objects.get(action=Action.CDR_IMPORT_REFUSED)
        assert refusal.reason == "import.conflict"


class TestTheDatabaseRulesBehindTheDedupe:
    """The application checks for repeats first, but a race or a future bug could skip that
    check. These rules in the database are the last line, so each one is pinned."""

    @pytest.fixture
    def stored(self) -> ImportBatch:
        return services.import_cdr(
            user=user_with(Role.PLANNER), file_name="x.xlsx", content=workbook_bytes(scenario())
        )

    def test_a_call_id_cannot_be_stored_twice(self, stored: ImportBatch) -> None:
        original = CallRecord.objects.get(call_id=1)
        with pytest.raises(IntegrityError), transaction.atomic():
            CallRecord.objects.create(
                call_id=1,
                batch=stored,
                queue=original.queue,
                call_type="INBOUND",
                status="Agent",
                start_at=original.start_at,
            )

    def test_a_file_cannot_be_recorded_twice(self, stored: ImportBatch) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            ImportBatch.objects.create(
                file_name="again.xlsx",
                sha256=stored.sha256,
                uploaded_by=stored.uploaded_by,
                source_timezone="UTC",
                period_start=stored.period_start,
                period_end=stored.period_end,
                rows_read=1,
                rows_inserted=1,
                rows_duplicate=0,
                rows_rejected=0,
            )

    def test_an_interval_cannot_be_stored_twice(self, stored: ImportBatch) -> None:
        existing = IntervalActual.objects.first()
        assert existing is not None
        with pytest.raises(IntegrityError), transaction.atomic():
            IntervalActual.objects.create(
                queue=existing.queue,
                interval_start=existing.interval_start,
                offered=1,
                answered=1,
                abandoned=0,
                answered_in_sl=1,
                sum_wait_s=0,
                sum_handle_s=0,
            )


class TestTheRulesAreNotTooStrict:
    """A guard that refuses legitimate data is as bad as one that is missing."""

    def test_a_later_month_with_the_same_number_of_rows_is_accepted(self) -> None:
        client = signed_in()
        assert client.post(IMPORTS, {"file": upload(workbook_bytes(scenario()))}).status_code == 201
        june = [
            Call(
                c.call_id + 1000, c.queue, c.status, c.start.replace("2026-05-04", "2026-06-04"),
                c.wait, c.talk, c.wrap, c.call_type,
            )
            for c in scenario()
        ]  # fmt: skip
        response = client.post(IMPORTS, {"file": upload(workbook_bytes(june), "june.xlsx")})
        assert response.status_code == 201, response.content
        assert CallRecord.objects.count() == 24
        assert ImportBatch.objects.count() == 2

    def test_a_re_export_of_the_same_dates_with_a_late_call_is_accepted(self) -> None:
        client = signed_in()
        assert client.post(IMPORTS, {"file": upload(workbook_bytes(scenario()))}).status_code == 201
        late = Call(50, "QueueA", "Agent", "2026-05-04 09:00:00", wait=2, talk=30, wrap=5)
        response = client.post(
            IMPORTS, {"file": upload(workbook_bytes([*scenario(), late]), "later.xlsx")}
        )
        assert response.status_code == 201, response.content
        assert (response.json()["rowsInserted"], response.json()["rowsDuplicate"]) == (1, 12)


class TestFileNames:
    @pytest.mark.parametrize(
        "name",
        ["../../etc/passwd.xlsx", "<script>alert(1)</script>.xlsx", "C:\\evil\\x.xlsx", "a" * 400],
    )
    def test_a_hostile_file_name_is_neutralised_before_it_is_stored_or_shown(
        self, name: str
    ) -> None:
        batch = services.import_cdr(
            user=user_with(Role.PLANNER), file_name=name, content=workbook_bytes(scenario())
        )
        assert not set(batch.file_name) & set("<>/\\:")
        assert 0 < len(batch.file_name) <= 255
