"""The sign-in endpoints with several providers configured (AUTH-02, AUTH-10, AUTH-11)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent
from wfm.identity import registry
from wfm.identity.providers.ldap import LdapProvider

from .test_ldap_provider import BASE, Directory, make_config

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse as TestResponse

pytestmark = pytest.mark.django_db

LDAP: dict[str, Any] = {
    "kind": "ldap",
    "key": "corp",
    "label": "Company directory",
    "server_uri": "ldaps://dc.example.org",
    "bind_dn": f"cn=svc,{BASE}",
    "bind_password_env": "LDAP_BIND_PASSWORD",
    "user_search_base": f"ou=people,{BASE}",
    "user_filter": "(uid={username})",
    "subject_attribute": "entryUUID",
    "username_attribute": "uid",
    "group_format": "cn",
    "provisioning": {
        "mode": "auto",
        "trust_attributes": True,
        "role_rules": [
            {"group": "WFM Planners", "role": "planner"},
            {"group": "WFM Agents", "role": "agent"},
        ],
    },
}
OIDC: dict[str, Any] = {
    "kind": "oidc",
    "key": "entra",
    "label": "Microsoft",
    "discovery_url": "https://idp.example.org/.well-known/openid-configuration",
    "client_id": "c",
    "client_secret_env": "OIDC_TEST_SECRET",
}


@pytest.fixture(autouse=True)
def secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LDAP_BIND_PASSWORD", "svc-secret")
    monkeypatch.setenv("OIDC_TEST_SECRET", "x")


@pytest.fixture
def directory() -> Directory:
    return Directory()


@pytest.fixture
def with_ldap(
    configure_identity: Callable[[list[dict[str, Any]]], None], directory: Directory
) -> Directory:
    configure_identity([LDAP, OIDC])
    registry._adapters["corp"] = LdapProvider(
        make_config(**{k: v for k, v in LDAP.items() if k in {"group_format"}}),
        connection_factory=directory.factory,
    )
    return directory


def browser() -> tuple[Client, str]:
    client = Client(enforce_csrf_checks=True)
    return client, client.get("/api/v1/auth/csrf").json()["csrfToken"]


def sign_in(
    client: Client, token: str, username: str, password: str, provider: str | None = None
) -> TestResponse:
    body: dict[str, str] = {"username": username, "password": password}
    if provider:
        body["provider"] = provider
    return client.post(
        "/api/v1/auth/login",
        data=body,
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )


class TestProviderList:
    def test_only_local_by_default(self, configure_identity: Callable[..., None]) -> None:
        configure_identity([])
        listed = Client().get("/api/v1/auth/providers").json()
        assert listed == [
            {
                "id": "local",
                "kind": "local",
                "label": "Username and password",
                "flow": "credentials",
                "startUrl": None,
                "restricted": False,
            }
        ]

    def test_each_kind_says_how_to_sign_in(self, with_ldap: Directory) -> None:
        listed = {p["id"]: p for p in Client().get("/api/v1/auth/providers").json()}

        assert listed["corp"]["flow"] == "credentials"
        assert listed["entra"]["flow"] == "redirect"
        assert listed["entra"]["startUrl"] == "/api/v1/auth/sso/entra/start"
        assert list(listed) == ["local", "corp", "entra"]

    def test_disabled_providers_are_not_offered(
        self, configure_identity: Callable[..., None]
    ) -> None:
        configure_identity([{**OIDC, "enabled": False}])
        ids = [p["id"] for p in Client().get("/api/v1/auth/providers").json()]
        assert ids == ["local"]

    def test_the_list_never_exposes_configuration_or_secrets(self, with_ldap: Directory) -> None:
        text = Client().get("/api/v1/auth/providers").content.decode()
        for private in ("svc-secret", "LDAP_BIND_PASSWORD", "client_id", "bind_dn", "dc.example"):
            assert private not in text

    def test_local_accounts_restricted_to_break_glass_are_flagged(
        self, configure_identity: Callable[..., None]
    ) -> None:
        configure_identity([{"kind": "local", "allowed_roles": ["admin"]}])
        (local,) = Client().get("/api/v1/auth/providers").json()
        assert local["restricted"] is True


class TestDirectorySignIn:
    def test_signs_in_through_the_directory_and_provisions_the_user(
        self, with_ldap: Directory
    ) -> None:
        client, token = browser()
        response = sign_in(client, token, "pat", "pat-secret", provider="corp")

        assert response.status_code == 200
        assert response.json()["role"] == "planner"  # from the "WFM Planners" group
        assert client.get("/api/v1/auth/me").json()["role"] == "planner"
        assert Action.SSO_LOGIN in AuditEvent.objects.values_list("action", flat=True)

    def test_a_directory_user_has_no_usable_local_password(self, with_ldap: Directory) -> None:
        client, token = browser()
        sign_in(client, token, "pat", "pat-secret", provider="corp")
        User.objects.get(username="pat")

        other, other_token = browser()
        for password in ("pat-secret", "", "anything"):
            attempt = sign_in(other, other_token, "pat", password)  # provider defaults to local
            assert attempt.status_code == 401

    def test_wrong_password_unknown_user_and_unknown_provider_are_indistinguishable(
        self, with_ldap: Directory
    ) -> None:
        client, token = browser()
        answers = [
            sign_in(client, token, "pat", "wrong", provider="corp"),
            sign_in(client, token, "nobody", "x", provider="corp"),
            sign_in(client, token, "pat", "pat-secret", provider="no-such-provider"),
            sign_in(client, token, "pat", "pat-secret", provider="entra"),  # redirect provider
        ]
        assert {a.status_code for a in answers} == {401}
        assert len({a.content for a in answers}) == 1  # byte-for-byte the same answer

    def test_the_real_reason_is_audited_without_the_typed_username(
        self, with_ldap: Directory
    ) -> None:
        client, token = browser()
        sign_in(client, token, "pat", "wrong", provider="corp")
        sign_in(client, token, "nobody-hunter2", "x", provider="corp")

        reasons = list(
            AuditEvent.objects.filter(action=Action.LOGIN_FAILED).values_list("reason", flat=True)
        )
        assert reasons == ["corp:bad_credentials", "corp:unknown_user"]
        assert "hunter2" not in " ".join(reasons)

    def test_an_empty_password_is_refused_and_never_reaches_the_directory(
        self, with_ldap: Directory
    ) -> None:
        client, token = browser()
        assert sign_in(client, token, "pat", "", provider="corp").status_code == 401
        assert with_ldap.binds == []

    def test_a_person_in_no_mapped_group_is_refused_and_no_account_is_created(
        self, with_ldap: Directory
    ) -> None:
        with_ldap.add_user("sam", "sam-secret", uuid="uuid-sam")  # in no group
        client, token = browser()

        assert sign_in(client, token, "sam", "sam-secret", provider="corp").status_code == 401

        assert not User.objects.filter(username="sam").exists()

    def test_a_broken_directory_configuration_says_so_without_leaking_details(
        self,
        with_ldap: Directory,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.delenv("LDAP_BIND_PASSWORD")
        client, token = browser()

        with caplog.at_level(logging.ERROR):
            response = sign_in(client, token, "pat", "pat-secret", provider="corp")

        assert response.status_code == 503
        assert response.json()["code"] == "auth.provider_unavailable"
        assert "LDAP_BIND_PASSWORD" not in response.content.decode()  # kept to the server log
        assert any("LDAP_BIND_PASSWORD" in r.message for r in caplog.records)

    def test_signing_in_needs_the_csrf_token_for_every_provider(self, with_ldap: Directory) -> None:
        client = Client(enforce_csrf_checks=True)
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "pat", "password": "pat-secret", "provider": "corp"},
            content_type="application/json",
        )
        assert response.status_code == 403


class TestLocalAccounts:
    def test_local_sign_in_still_works_with_other_providers_configured(
        self, with_ldap: Directory
    ) -> None:
        User.objects.create_user(
            username="local-admin", password="a-strong-password", role=Role.ADMIN
        )
        client, token = browser()
        assert sign_in(client, token, "local-admin", "a-strong-password").status_code == 200

    def test_production_can_restrict_local_accounts_to_break_glass_roles(
        self, configure_identity: Callable[..., None]
    ) -> None:
        configure_identity([{"kind": "local", "allowed_roles": ["admin"]}])
        User.objects.create_user(username="pat", password="a-strong-password", role=Role.PLANNER)
        User.objects.create_user(username="root", password="a-strong-password", role=Role.ADMIN)
        client, token = browser()

        planner = sign_in(client, token, "pat", "a-strong-password")
        admin = sign_in(client, token, "root", "a-strong-password")

        assert planner.status_code == 401  # correct password, but must use the organisation's SSO
        assert admin.status_code == 200
        assert "local_login_not_allowed_for_role" in AuditEvent.objects.filter(
            action=Action.LOGIN_FAILED
        ).values_list("reason", flat=True)

    def test_a_restricted_refusal_looks_the_same_as_a_wrong_password(
        self, configure_identity: Callable[..., None]
    ) -> None:
        configure_identity([{"kind": "local", "allowed_roles": ["admin"]}])
        User.objects.create_user(username="pat", password="a-strong-password", role=Role.PLANNER)
        client, token = browser()
        refused = sign_in(client, token, "pat", "a-strong-password")
        wrong = sign_in(client, token, "pat", "nope")
        assert refused.content == wrong.content
