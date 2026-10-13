"""The LDAP adapter against ldap3's in-memory mock server: protocol behaviour and the safety rules
(AUTH-09). A real OpenLDAP container test follows in test_ldap_real.py."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from ldap3 import MOCK_SYNC, Connection, Server
from ldap3.core.exceptions import LDAPSocketOpenError

from wfm.identity.config import LdapConfig
from wfm.identity.providers.ldap import LdapProvider
from wfm.identity.types import AuthenticationFailedError, ProviderMisconfiguredError

BASE = "dc=example,dc=org"
SVC_DN = f"cn=svc,{BASE}"
PLANNERS = f"cn=WFM Planners,ou=groups,{BASE}"
AGENTS = f"cn=WFM Agents,ou=groups,{BASE}"


@pytest.fixture(autouse=True)
def bind_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LDAP_BIND_PASSWORD", "svc-secret")


def make_config(**overrides: object) -> LdapConfig:
    base: dict[str, object] = {
        "key": "corp",
        "label": "Corp",
        "server_uri": "ldaps://dc.example.org",
        "bind_dn": SVC_DN,
        "bind_password_env": "LDAP_BIND_PASSWORD",
        "user_search_base": f"ou=people,{BASE}",
        "user_filter": "(uid={username})",
        "subject_attribute": "entryUUID",
        "username_attribute": "uid",
    }
    return LdapConfig(**{**base, **overrides})  # type: ignore[arg-type]


class Directory:
    """An in-memory directory plus a factory that hands out connections to it, counting binds."""

    def __init__(self) -> None:
        self.server = Server("mock-directory")
        self.binds: list[str | None] = []
        admin = Connection(
            self.server, user=SVC_DN, password="svc-secret", client_strategy=MOCK_SYNC
        )
        admin.strategy.add_entry(SVC_DN, {"userPassword": "svc-secret", "objectClass": "person"})
        self._admin = admin
        self.add_user("pat", "pat-secret", uuid="uuid-pat", groups=[PLANNERS])

    def add_user(
        self, uid: str, password: str, *, uuid: str, groups: list[str] | None = None
    ) -> None:
        attributes: dict[str, object] = {
            "uid": uid,
            "userPassword": password,
            "objectClass": "person",
            "entryUUID": uuid,
            "mail": f"{uid}@example.org",
            "displayName": uid.title() + " Example",
        }
        if groups:
            attributes["memberOf"] = groups
        self._admin.strategy.add_entry(f"uid={uid},ou=people,{BASE}", attributes)

    def add_group(self, dn: str, members: list[str]) -> None:
        self._admin.strategy.add_entry(dn, {"objectClass": "group", "member": members})

    def factory(self, user: str | None, password: str | None) -> Connection:
        self.binds.append(user)
        return Connection(self.server, user=user, password=password, client_strategy=MOCK_SYNC)


@pytest.fixture
def directory() -> Directory:
    return Directory()


def provider(directory: Directory, **overrides: object) -> LdapProvider:
    return LdapProvider(make_config(**overrides), connection_factory=directory.factory)


class TestSuccessfulSignIn:
    def test_returns_the_identity_with_a_stable_subject(self, directory: Directory) -> None:
        identity = provider(directory).authenticate("pat", "pat-secret")

        assert identity.provider == "corp"
        assert identity.subject == "uuid-pat"
        assert identity.username == "pat"
        assert identity.email == "pat@example.org"
        assert identity.email_verified is True  # the directory is the authority on its own mail
        assert identity.display_name == "Pat Example"

    def test_groups_come_from_member_of_by_default(self, directory: Directory) -> None:
        identity = provider(directory).authenticate("pat", "pat-secret")
        assert identity.groups == (PLANNERS,)

    def test_groups_can_be_reduced_to_their_common_name(self, directory: Directory) -> None:
        identity = provider(directory, group_format="cn").authenticate("pat", "pat-secret")
        assert identity.groups == ("WFM Planners",)

    def test_groups_can_come_from_a_group_search_instead(self, directory: Directory) -> None:
        directory.add_user("sam", "sam-secret", uuid="uuid-sam")  # no memberOf attribute
        directory.add_group(AGENTS, [f"uid=sam,ou=people,{BASE}"])
        cfg = {"group_base": f"ou=groups,{BASE}", "group_filter": "(member={user_dn})"}

        identity = provider(directory, **cfg).authenticate("sam", "sam-secret")

        assert identity.groups == (AGENTS,)

    def test_a_user_in_no_group_has_no_groups(self, directory: Directory) -> None:
        directory.add_user("sam", "sam-secret", uuid="uuid-sam")
        assert provider(directory).authenticate("sam", "sam-secret").groups == ()

    def test_the_password_is_checked_by_binding_as_the_user_not_by_comparing(
        self, directory: Directory
    ) -> None:
        provider(directory).authenticate("pat", "pat-secret")
        assert directory.binds == [SVC_DN, f"uid=pat,ou=people,{BASE}"]


class TestRefusals:
    @pytest.mark.parametrize(
        ("username", "password", "reason"),
        [
            ("pat", "wrong", "bad_credentials"),
            ("nobody", "x", "unknown_user"),
            ("pat", "", "empty_credentials"),
            ("", "pat-secret", "empty_credentials"),
            ("", "", "empty_credentials"),
        ],
    )
    def test_refused_with_an_internal_reason_code(
        self, directory: Directory, username: str, password: str, reason: str
    ) -> None:
        with pytest.raises(AuthenticationFailedError) as refused:
            provider(directory).authenticate(username, password)
        assert refused.value.reason == reason

    def test_an_empty_password_never_reaches_the_directory(self, directory: Directory) -> None:
        """A simple bind with an empty password succeeds anonymously on many servers, which would
        sign in anyone who knows a username. It must be refused before any bind happens."""
        with pytest.raises(AuthenticationFailedError):
            provider(directory).authenticate("pat", "")
        assert directory.binds == []

    def test_overlong_input_is_refused_before_it_reaches_the_directory(
        self, directory: Directory
    ) -> None:
        with pytest.raises(AuthenticationFailedError):
            provider(directory).authenticate("p" * 600, "x")
        assert directory.binds == []

    @pytest.mark.parametrize("hostile", ["*", "pat)(uid=*", "*)(objectClass=*", "pat\\", "\x00"])
    def test_filter_injection_cannot_match_other_people(
        self, directory: Directory, hostile: str
    ) -> None:
        directory.add_user("sam", "sam-secret", uuid="uuid-sam")
        with pytest.raises(AuthenticationFailedError) as refused:
            provider(directory).authenticate(hostile, "anything")
        assert refused.value.reason in {"unknown_user", "bad_credentials"}

    def test_two_matching_users_is_refused_not_resolved_by_picking_one(
        self, directory: Directory
    ) -> None:
        directory._admin.strategy.add_entry(
            f"uid=pat2,ou=other,{BASE}",
            {"uid": "pat", "userPassword": "x", "objectClass": "person", "entryUUID": "uuid-2"},
        )
        cfg = make_config(user_search_base=BASE)
        with pytest.raises(AuthenticationFailedError) as refused:
            LdapProvider(cfg, connection_factory=directory.factory).authenticate(
                "pat", "pat-secret"
            )
        assert refused.value.reason == "ambiguous_user"

    def test_a_user_without_a_stable_id_cannot_be_linked_and_is_refused(
        self, directory: Directory
    ) -> None:
        directory._admin.strategy.add_entry(
            f"uid=ghost,ou=people,{BASE}",
            {"uid": "ghost", "userPassword": "x", "objectClass": "person"},
        )
        with pytest.raises(AuthenticationFailedError) as refused:
            provider(directory).authenticate("ghost", "x")
        assert refused.value.reason == "no_subject"

    def test_a_wrong_service_account_password_is_a_directory_error(
        self, directory: Directory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LDAP_BIND_PASSWORD", "wrong")
        with pytest.raises(AuthenticationFailedError) as refused:
            provider(directory).authenticate("pat", "pat-secret")
        assert refused.value.reason == "directory_error:service_bind"

    def test_network_failures_become_a_refusal_never_a_crash(self) -> None:
        def unreachable(user: str | None, password: str | None) -> Connection:
            raise LDAPSocketOpenError("connection refused")

        cfg = make_config()
        with pytest.raises(AuthenticationFailedError) as refused:
            LdapProvider(cfg, connection_factory=unreachable).authenticate("pat", "x")
        assert refused.value.reason == "directory_error:LDAPSocketOpenError"


class TestConfigurationSafety:
    def test_plain_ldap_without_tls_is_refused_at_start_up(self) -> None:
        with pytest.raises(ProviderMisconfiguredError, match="unencrypted"):
            LdapProvider(make_config(server_uri="ldap://dc.example.org"))

    def test_plain_ldap_is_allowed_when_explicitly_marked_insecure_for_development(self) -> None:
        LdapProvider(make_config(server_uri="ldap://localhost", allow_insecure=True))

    def test_plain_ldap_is_allowed_with_start_tls(self) -> None:
        LdapProvider(make_config(server_uri="ldap://dc.example.org", start_tls=True))

    def test_ldaps_needs_nothing_extra(self) -> None:
        LdapProvider(make_config(server_uri="ldaps://dc.example.org"))

    def test_a_missing_service_password_is_a_deployment_error(
        self, directory: Directory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LDAP_BIND_PASSWORD")
        with pytest.raises(ProviderMisconfiguredError, match="LDAP_BIND_PASSWORD"):
            provider(directory).authenticate("pat", "pat-secret")


FACTORY_TYPE = Callable[[str | None, str | None], Connection]
