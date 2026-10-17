"""Call data keyed by an ACD login (DAT-01) in the subject-access export and in erasure (POPIA).

The detail tables hold agent LOGINS. The export gives the person their own rows and nobody else's;
erasure replaces their logins with a random token and leaves everyone else's rows alone."""

from __future__ import annotations

import json
from typing import Any

import pytest

from wfm.accounts.models import Role
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.scheduling.import_services import unmapped_logins
from wfm.scheduling.models import AgentLogin
from wfm.scheduling.tests.helpers import person, queue
from wfm.telephony.models import AgentOffer, CallRecord, CallTransfer
from wfm.telephony.tests import factories as f

from .test_erasure_api import LOGIN, NUMBER, client, confirm, leaver, preview_url

pytestmark = pytest.mark.django_db

OTHER_LOGIN = "colleague7"


def seed() -> tuple[Any, Any]:
    """The leaver (login `pleaverson`) and a colleague, each with calls, offers and a transfer."""
    mine = leaver()
    colleague = person("E888", name="Olly Other")
    AgentLogin.objects.create(login=OTHER_LOGIN, employee=colleague)
    q = queue()
    c1 = f.call(q, agent=LOGIN)
    f.offer(c1, LOGIN, answered=True, ring_s=7)
    f.offer(c1, OTHER_LOGIN, answered=False, ring_s=20)
    f.transfer(c1, LOGIN, answer_s=4, duration_s=90)
    f.disposition(c1, "INC000000000123")
    f.pause(c1, "hold", 30)
    c2 = f.call(q, agent=OTHER_LOGIN)
    f.offer(c2, OTHER_LOGIN, answered=True, ring_s=3)
    f.offer(c2, LOGIN, answered=False, ring_s=15)
    f.transfer(c2, OTHER_LOGIN, answer_s=8, duration_s=40)
    return mine, colleague


def export(pk: int) -> Any:
    return client(Role.ADMIN).get(f"/api/v1/people/employees/{pk}/data-export")


class TestExport:
    def test_it_holds_the_persons_own_offers_and_transfers_and_counts(self) -> None:
        mine, _ = seed()
        data = json.loads(export(mine.pk).content)
        assert data["callData"] == {
            "callsHandled": 1,
            "dispositions": 1,
            "mutesAndHolds": 1,
            "offers": 2,
            "transfers": 1,
        }
        assert sorted(o["ringSeconds"] for o in data["callOffers"]) == [7, 15]
        assert data["callTransfers"] == [
            {"queue": "QueueA", "secondsToAnswer": 4, "secondsTalked": 90}
        ]

    def test_it_holds_nothing_of_another_agent(self) -> None:
        # Failure caught: the colleague's offers, logins or transfers in someone else's file.
        mine, _ = seed()
        text = export(mine.pk).content.decode()
        assert OTHER_LOGIN not in text
        assert "Olly Other" not in text
        data = json.loads(text)
        assert 20 not in [o["ringSeconds"] for o in data["callOffers"]]
        assert 40 not in [t["secondsTalked"] for t in data["callTransfers"]]

    def test_a_person_with_no_login_has_no_call_data(self) -> None:
        seed()
        lone = person("E999", name="No Login")
        data = json.loads(export(lone.pk).content)
        assert data["callData"] == {}
        assert data["callOffers"] == []
        assert data["callTransfers"] == []

    @pytest.mark.parametrize(
        "role", [Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]
    )
    def test_every_other_role_is_refused(self, role: Role) -> None:
        mine, _ = seed()
        assert (
            client(role).get(f"/api/v1/people/employees/{mine.pk}/data-export").status_code == 403
        )


class TestErasure:
    def test_the_preview_counts_the_login_keyed_rows(self) -> None:
        mine, _ = seed()
        body = client(Role.ADMIN).post(preview_url(mine.pk)).json()
        assert body["removes"]["callRecordLogins"] == 1
        assert body["removes"]["offerLogins"] == 2
        assert body["removes"]["transferLogins"] == 1
        assert AgentOffer.objects.filter(agent_login=LOGIN).count() == 2  # preview changes nothing

    @pytest.mark.parametrize(
        "role", [Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]
    )
    def test_every_other_role_is_refused(self, role: Role) -> None:
        mine, _ = seed()
        assert client(role).post(preview_url(mine.pk)).status_code == 403
        assert confirm(mine.pk, NUMBER, role).status_code == 403
        assert AgentOffer.objects.filter(agent_login=LOGIN).count() == 2

    def test_erasing_one_person_leaves_everyone_elses_rows_untouched(self) -> None:
        # Failure caught: a broad update that renames the colleague's logins too, or deletes
        # offers, so their ring-no-answer figures change when someone else is erased.
        mine, colleague = seed()
        others_before = {
            "calls": list(CallRecord.objects.filter(agent_login=OTHER_LOGIN).values_list("pk")),
            "offers": list(AgentOffer.objects.filter(agent_login=OTHER_LOGIN).values_list("pk")),
            "transfers": list(CallTransfer.objects.filter(by_login=OTHER_LOGIN).values_list("pk")),
        }
        totals = (
            CallRecord.objects.count(),
            AgentOffer.objects.count(),
            CallTransfer.objects.count(),
        )
        assert confirm(mine.pk, NUMBER).status_code == 200

        assert not CallRecord.objects.filter(agent_login=LOGIN).exists()
        assert not AgentOffer.objects.filter(agent_login=LOGIN).exists()
        assert not CallTransfer.objects.filter(by_login=LOGIN).exists()
        assert (
            list(CallRecord.objects.filter(agent_login=OTHER_LOGIN).values_list("pk"))
            == others_before["calls"]
        )
        assert (
            list(AgentOffer.objects.filter(agent_login=OTHER_LOGIN).values_list("pk"))
            == others_before["offers"]
        )
        assert (
            list(CallTransfer.objects.filter(by_login=OTHER_LOGIN).values_list("pk"))
            == others_before["transfers"]
        )
        # Nothing was deleted: only the login changed, so counts per queue and day do not move.
        assert (
            CallRecord.objects.count(),
            AgentOffer.objects.count(),
            CallTransfer.objects.count(),
        ) == totals
        assert AgentLogin.objects.filter(employee=colleague, login=OTHER_LOGIN).exists()

    def test_the_replaced_login_is_one_token_for_the_person_and_not_the_old_login(self) -> None:
        mine, _ = seed()
        confirm(mine.pk, NUMBER)
        tokens = set(
            AgentOffer.objects.exclude(agent_login=OTHER_LOGIN).values_list(
                "agent_login", flat=True
            )
        ) | set(
            CallRecord.objects.filter(agent_login__startswith="erased-").values_list(
                "agent_login", flat=True
            )
        )
        assert len(tokens) == 1
        assert next(iter(tokens)).startswith("erased-")
        assert LOGIN not in next(iter(tokens))

    def test_the_replaced_login_is_not_offered_as_an_unmapped_login(self) -> None:
        mine, _ = seed()
        confirm(mine.pk, NUMBER)
        assert [u.login for u in unmapped_logins()] == []

    def test_the_audit_event_holds_counts_only_and_no_login(self) -> None:
        mine, _ = seed()
        confirm(mine.pk, NUMBER)
        event = AuditEvent.objects.filter(action=Action.EMPLOYEE_ANONYMISED).get()
        changes = {c.field: c.new_value for c in AuditChange.objects.filter(event=event)}
        assert changes["removed_offerLogins"] == "2"
        assert changes["removed_callRecordLogins"] == "1"
        assert changes["removed_transferLogins"] == "1"
        assert LOGIN not in json.dumps(changes)
        assert AuditEvent.objects.order_by("-pk").first() == event  # the last write
