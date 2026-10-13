"""OpenID Connect sign-in end to end against a fake provider that signs real tokens (AUTH-08).

Every failure must look the same to the user (a redirect to the login page with a generic error)
while the audit trail records the real reason."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from authlib.jose import JsonWebKey
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent
from wfm.identity.models import IdentityLink

from .fake_idp import CLIENT_ID, ISSUER, TENANT, FakeIdp, Flow

pytestmark = pytest.mark.django_db

FAILED = "/login?error=sso_failed"

CONFIG: dict[str, Any] = {
    "kind": "oidc",
    "key": "entra",
    "label": "Microsoft",
    "discovery_url": f"{ISSUER}/.well-known/openid-configuration",
    "issuer": ISSUER,
    "client_id": CLIENT_ID,
    "client_secret_env": "OIDC_TEST_SECRET",
    "tenant_id": TENANT,
    "subject_claim": "oid",
    "provisioning": {
        "mode": "auto",
        "trust_attributes": True,
        "role_rules": [
            {"group": "WFM Planners", "role": "planner"},
            {"group": "WFM Admins", "role": "admin"},
        ],
    },
}


@pytest.fixture(autouse=True)
def secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_TEST_SECRET", "the-client-secret")


@pytest.fixture
def rsps() -> Iterator[responses.RequestsMock]:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.fixture
def idp() -> FakeIdp:
    return FakeIdp()


@pytest.fixture
def flow(
    configure_identity: Callable[[list[dict[str, Any]]], None],
    idp: FakeIdp,
    rsps: responses.RequestsMock,
) -> Flow:
    configure_identity([CONFIG])
    return Flow(Client(), idp, rsps)


def me(flow: Flow) -> Any:
    return flow.client.get("/api/v1/auth/me")


def reasons() -> list[str]:
    return [
        e.reason
        for e in AuditEvent.objects.filter(
            action__in=[Action.LOGIN_FAILED, Action.SSO_DENIED]
        ).order_by("chain_seq")
    ]


class TestStart:
    def test_redirects_to_the_provider_with_every_protection_switched_on(self, flow: Flow) -> None:
        response = flow.start()

        assert response.status_code == 302
        query = parse_qs(urlparse(response["Location"]).query)
        assert response["Location"].startswith(f"{ISSUER}/authorize")
        assert query["response_type"] == ["code"]  # authorisation-code flow, never implicit
        assert query["client_id"] == [CLIENT_ID]
        assert query["code_challenge_method"] == ["S256"]  # PKCE
        assert len(query["code_challenge"][0]) >= 43
        assert len(query["state"][0]) >= 16
        assert len(query["nonce"][0]) >= 16
        assert "openid" in query["scope"][0].split()
        assert query["redirect_uri"] == ["http://testserver/api/v1/auth/sso/entra/callback"]

    def test_state_and_nonce_are_fresh_for_every_attempt(self, flow: Flow) -> None:
        flow.start()
        first = (flow.state, flow.nonce["value"], flow.challenge)
        flow.start()
        assert (flow.state, flow.nonce["value"], flow.challenge) != first

    def test_the_public_base_url_overrides_the_request_host(
        self, flow: Flow, settings: Any
    ) -> None:
        settings.WFM_PUBLIC_BASE_URL = "https://wfm.gijima.example"
        flow.start()
        query = parse_qs(urlparse(flow.location).query)
        assert query["redirect_uri"] == [
            "https://wfm.gijima.example/api/v1/auth/sso/entra/callback"
        ]

    def test_an_unknown_provider_is_a_404(self, flow: Flow) -> None:
        assert flow.client.get("/api/v1/auth/sso/nope/start").status_code == 404

    def test_an_unreachable_provider_sends_the_user_back_with_the_generic_error(
        self, configure_identity: Callable[[list[dict[str, Any]]], None]
    ) -> None:
        configure_identity([CONFIG])
        with responses.RequestsMock() as mock:
            mock.add(responses.GET, f"{ISSUER}/.well-known/openid-configuration", status=503)
            response = Client().get("/api/v1/auth/sso/entra/start")

        assert response.status_code == 302
        assert response["Location"] == FAILED
        assert any("start_failed" in r for r in reasons())


class TestSuccessfulSignIn:
    def test_signs_the_user_in_provisions_them_and_returns_to_where_they_were_going(
        self, flow: Flow
    ) -> None:
        flow.start("/roster")

        response = flow.callback()

        assert response.status_code == 302
        assert response["Location"] == "/roster"
        who = me(flow)
        assert who.status_code == 200
        assert who.json()["role"] == "planner"
        assert who.json()["displayName"] == "Pat Planner"
        link = IdentityLink.objects.get()
        assert (link.provider, link.subject) == ("entra", "object-id-1")  # linked by oid, not name
        assert Action.SSO_LOGIN in AuditEvent.objects.values_list("action", flat=True)

    def test_the_code_exchange_proves_possession_with_pkce_and_the_client_secret(
        self, flow: Flow
    ) -> None:
        flow.start()
        flow.callback()

        request = flow.idp.token_requests[-1]
        assert request["grant_type"] == ["authorization_code"]
        assert request["code"] == ["auth-code"]
        assert flow.verifier_matches_challenge()  # the verifier hashes to the challenge sent first

    def test_the_next_address_is_kept_only_when_it_is_a_same_site_path(self, flow: Flow) -> None:
        flow.start("https://evil.example/phish")
        assert flow.callback()["Location"] == "/"

    def test_roles_follow_the_groups_in_the_token(self, flow: Flow) -> None:
        flow.idp.claims = {"groups": ["WFM Planners", "WFM Admins"]}
        flow.start()
        flow.callback()
        assert me(flow).json()["role"] == "admin"  # most privileged match wins

    def test_a_second_visit_updates_the_role_when_the_groups_changed(self, flow: Flow) -> None:
        flow.start()
        flow.callback()
        flow.client.post(
            "/api/v1/auth/logout", HTTP_X_CSRFTOKEN=flow.client.cookies["csrftoken"].value
        )

        flow.idp.claims = {"groups": ["WFM Admins"]}
        flow.start()
        flow.callback()

        assert User.objects.count() == 1
        assert User.objects.get().role == Role.ADMIN
        assert Action.ROLE_CHANGED in AuditEvent.objects.values_list("action", flat=True)


@pytest.mark.parametrize(
    ("name", "claims", "reason_prefix"),
    [
        ("expired token", {"exp": 1_000_000_000}, "token_invalid"),
        ("wrong audience", {"aud": "someone-elses-client"}, "token_invalid"),
        ("wrong issuer", {"iss": "https://evil.example/tenant-1/v2.0"}, "token_invalid"),
        ("wrong nonce", {"nonce": "not-the-one-we-sent"}, "token_invalid"),
        ("another organisation's tenant", {"tid": "tenant-EVIL"}, "wrong_tenant"),
        ("no stable subject", {"oid": None}, "no_subject"),
        ("no groups at all", {"groups": None}, "no_role"),
        ("groups we do not map", {"groups": ["Cafeteria"]}, "no_role"),
    ],
)
def test_a_bad_token_is_refused_generically_and_for_a_recorded_reason(
    flow: Flow, name: str, claims: dict[str, Any], reason_prefix: str
) -> None:
    flow.idp.claims = claims
    flow.start()

    response = flow.callback()

    assert response.status_code == 302, name
    assert response["Location"] == FAILED, name  # the same answer for every failure
    assert me(flow).status_code == 401, name  # nobody was signed in
    assert User.objects.count() == 0, name  # and nothing was created
    assert any(reason_prefix in r for r in reasons()), (name, reasons())


class TestAttacksOnTheFlow:
    def test_a_tampered_state_is_refused(self, flow: Flow) -> None:
        flow.start()
        response = flow.callback(state="attacker-chosen-state")
        assert response["Location"] == FAILED
        assert me(flow).status_code == 401
        assert any("state" in r for r in reasons())

    def test_a_callback_without_a_started_flow_is_refused(self, flow: Flow) -> None:
        # e.g. a link an attacker sent: there is no state in this browser's session
        response = flow.callback(state="whatever")
        assert response["Location"] == FAILED
        assert User.objects.count() == 0

    def test_a_token_signed_by_the_wrong_key_is_refused(self, flow: Flow) -> None:
        other = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "key-1"})
        flow.idp.pending_id_token = lambda nonce: flow.idp.id_token(  # type: ignore[method-assign]
            key=other, nonce=nonce["value"]
        )
        flow.start()
        assert flow.callback()["Location"] == FAILED
        assert User.objects.count() == 0
        assert any("token_invalid" in r for r in reasons())

    def test_the_same_callback_cannot_be_replayed(self, flow: Flow) -> None:
        flow.start()
        assert flow.callback()["Location"] == "/"
        flow.client.post(
            "/api/v1/auth/logout", HTTP_X_CSRFTOKEN=flow.client.cookies["csrftoken"].value
        )

        replay = flow.callback()  # same code and state again

        assert replay["Location"] == FAILED
        assert me(flow).status_code == 401

    def test_an_error_from_the_provider_is_refused_without_leaking_it(self, flow: Flow) -> None:
        flow.start()
        response = flow.client.get(
            "/api/v1/auth/sso/entra/callback",
            {"error": "access_denied", "error_description": "user said no", "state": flow.state},
        )
        assert response["Location"] == FAILED
        assert "user said no" not in response["Location"]
        assert any("access_denied" in r for r in reasons())

    def test_a_provider_outage_during_the_code_exchange_is_a_generic_failure(
        self, flow: Flow
    ) -> None:
        flow.idp.token_status = 500
        flow.start()
        assert flow.callback()["Location"] == FAILED
        assert User.objects.count() == 0


class TestPolicy:
    def test_an_email_domain_allow_list_refuses_other_domains(
        self,
        configure_identity: Callable[[list[dict[str, Any]]], None],
        idp: FakeIdp,
        rsps: responses.RequestsMock,
    ) -> None:
        configure_identity([{**CONFIG, "allowed_email_domains": ["gijima.example"]}])
        flow = Flow(Client(), idp, rsps)
        flow.start()
        assert flow.callback()["Location"] == FAILED
        assert any("email_domain_not_allowed" in r for r in reasons())

    def test_group_overage_is_logged_and_treated_as_no_groups(
        self, flow: Flow, caplog: pytest.LogCaptureFixture
    ) -> None:
        flow.idp.claims = {
            "groups": None,
            "_claim_names": {"groups": "src1"},
            "_claim_sources": {
                "src1": {"endpoint": "https://graph.example/users/x/getMemberObjects"}
            },
        }
        flow.start()
        with caplog.at_level(logging.WARNING):
            response = flow.callback()
        assert response["Location"] == FAILED  # no groups, no default role
        assert any("overage" in r.message for r in caplog.records)

    def test_login_is_refused_for_a_user_deactivated_in_the_application(self, flow: Flow) -> None:
        flow.start()
        flow.callback()
        User.objects.update(is_active=False)
        flow.client.cookies.clear()

        flow.start()
        assert flow.callback()["Location"] == FAILED
        assert me(flow).status_code == 401
