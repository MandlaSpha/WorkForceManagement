"""The LDAP adapter against a REAL OpenLDAP server in a container (AUTH-15).

The mock directory in test_ldap_provider.py shares our own assumptions about how LDAP behaves; a
real server does not. This is where those assumptions are checked, including the one the empty
password rule exists for.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from ldap3 import ALL, Connection, Server
from ldap3.core.exceptions import LDAPPasswordIsMandatoryError
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from wfm.identity.config import LdapConfig
from wfm.identity.providers.ldap import LdapProvider
from wfm.identity.types import AuthenticationFailedError

BASE = "dc=example,dc=org"
ADMIN_DN = f"cn=admin,{BASE}"
ADMIN_PASSWORD = "admin-secret"
PEOPLE = f"ou=people,{BASE}"
GROUPS = f"ou=groups,{BASE}"


@pytest.fixture(scope="module")
def ldap_url() -> Iterator[str]:
    container = (
        DockerContainer("osixia/openldap:1.5.0")
        .with_env("LDAP_ORGANISATION", "Example")
        .with_env("LDAP_DOMAIN", "example.org")
        .with_env("LDAP_ADMIN_PASSWORD", ADMIN_PASSWORD)
        .with_env("LDAP_TLS", "false")
        .with_exposed_ports(389)
    )
    with container:
        wait_for_logs(container, "slapd starting", timeout=60)
        url = f"ldap://{container.get_container_host_ip()}:{container.get_exposed_port(389)}"
        _populate(url)
        yield url


def _populate(url: str) -> None:
    conn = Connection(Server(url), user=ADMIN_DN, password=ADMIN_PASSWORD, auto_bind=True)

    def add(dn: str, classes: list[str], attrs: dict[str, object]) -> None:
        assert conn.add(dn, classes, attrs), conn.result

    add(PEOPLE, ["organizationalUnit"], {"ou": "people"})
    add(GROUPS, ["organizationalUnit"], {"ou": "groups"})
    for uid, password in (("pat", "pat-secret"), ("sam", "sam-secret")):
        add(
            f"uid={uid},{PEOPLE}",
            ["inetOrgPerson"],
            {
                "uid": uid,
                "cn": uid.title(),
                "sn": "Example",
                "mail": f"{uid}@example.org",
                "displayName": f"{uid.title()} Example",
                "userPassword": password,
            },
        )
    add(
        f"cn=WFM Planners,{GROUPS}",
        ["groupOfNames"],
        {"cn": "WFM Planners", "member": [f"uid=pat,{PEOPLE}"]},
    )
    conn.unbind()


@pytest.fixture
def provider(ldap_url: str, monkeypatch: pytest.MonkeyPatch) -> LdapProvider:
    monkeypatch.setenv("LDAP_REAL_BIND_PASSWORD", ADMIN_PASSWORD)
    cfg = LdapConfig(
        key="real",
        label="Real",
        server_uri=ldap_url,
        allow_insecure=True,  # plain ldap:// to a throwaway container; refused anywhere else
        bind_dn=ADMIN_DN,
        bind_password_env="LDAP_REAL_BIND_PASSWORD",
        user_search_base=PEOPLE,
        user_filter="(uid={username})",
        subject_attribute="entryUUID",
        username_attribute="uid",
        group_base=GROUPS,
        group_filter="(member={user_dn})",
        group_format="cn",
        groups_from_member_of=False,
    )
    return LdapProvider(cfg)


def test_a_real_server_authenticates_a_user_and_returns_a_stable_id(provider: LdapProvider) -> None:
    identity = provider.authenticate("pat", "pat-secret")

    assert identity.username == "pat"
    assert identity.email == "pat@example.org"
    assert identity.display_name == "Pat Example"
    assert len(identity.subject) == 36  # an entryUUID, not a name that can change
    assert identity.groups == ("WFM Planners",)


def test_the_subject_is_stable_between_sign_ins(provider: LdapProvider) -> None:
    assert (
        provider.authenticate("pat", "pat-secret").subject
        == provider.authenticate("pat", "pat-secret").subject
    )


def test_two_people_get_different_subjects(provider: LdapProvider) -> None:
    assert (
        provider.authenticate("pat", "pat-secret").subject
        != provider.authenticate("sam", "sam-secret").subject
    )


def test_a_user_in_no_group_has_no_groups(provider: LdapProvider) -> None:
    assert provider.authenticate("sam", "sam-secret").groups == ()


@pytest.mark.parametrize(
    ("username", "password", "reason"),
    [
        ("pat", "wrong", "bad_credentials"),
        ("nobody", "x", "unknown_user"),
        ("*", "x", "unknown_user"),  # a wildcard must not match everyone
        ("pat)(uid=*", "x", "unknown_user"),  # filter injection
        ("pat", "", "empty_credentials"),
    ],
)
def test_a_real_server_refuses_what_it_should(
    provider: LdapProvider, username: str, password: str, reason: str
) -> None:
    with pytest.raises(AuthenticationFailedError) as refused:
        provider.authenticate(username, password)
    assert refused.value.reason == reason


def test_an_empty_password_is_stopped_twice(ldap_url: str) -> None:
    """RFC 4513 lets a server treat a simple bind with a DN and an EMPTY password as an
    "unauthenticated bind" that succeeds, so a sign-in that only asked "did the bind work?" would
    admit anyone who knows a username. Two things stop it here: the adapter refuses empty passwords
    before any network call (tested above), and ldap3 itself refuses to send one, as shown now.

    That second guard is a property of ldap3, not of the protocol, so the adapter's own rule stays:
    a library upgrade or a different client must not be able to reopen the hole."""
    raw = Connection(Server(ldap_url), user=f"uid=pat,{PEOPLE}", password="")
    with pytest.raises(LDAPPasswordIsMandatoryError):
        raw.bind()


def test_the_server_is_really_what_we_think_it_is(ldap_url: str) -> None:
    server = Server(ldap_url, get_info=ALL)
    with Connection(server, user=ADMIN_DN, password=ADMIN_PASSWORD, auto_bind=True) as conn:
        assert conn.search(PEOPLE, "(objectClass=inetOrgPerson)", attributes=["uid"])
        assert {str(e.uid) for e in conn.entries} == {"pat", "sam"}


def test_the_demo_directory_seed_command_creates_people_that_can_sign_in(
    ldap_url: str, monkeypatch: pytest.MonkeyPatch, settings: object
) -> None:
    """The dev-stack seed command, run twice against a real server: it works, it is idempotent,
    and the people it creates can authenticate and land in the groups the role rules expect."""
    from django.core.management import call_command

    settings.DEBUG = True  # type: ignore[attr-defined]
    monkeypatch.setenv("LDAP_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("WFM_DEMO_PASSWORD", "first-demo-password")
    call_command("seed_demo_directory", uri=ldap_url, wait_s=10)
    monkeypatch.setenv("WFM_DEMO_PASSWORD", "second-demo-password")
    call_command("seed_demo_directory", uri=ldap_url, wait_s=10)  # idempotent, rotates passwords

    monkeypatch.setenv("LDAP_REAL_BIND_PASSWORD", ADMIN_PASSWORD)
    cfg = LdapConfig(
        key="real",
        label="Real",
        server_uri=ldap_url,
        allow_insecure=True,
        bind_dn=ADMIN_DN,
        bind_password_env="LDAP_REAL_BIND_PASSWORD",
        user_search_base=PEOPLE,
        user_filter="(uid={username})",
        subject_attribute="entryUUID",
        username_attribute="uid",
        group_base=GROUPS,
        group_format="cn",
        groups_from_member_of=False,
    )
    seeded = LdapProvider(cfg)

    assert seeded.authenticate("ash", "second-demo-password").groups == ("WFM Admins",)
    assert seeded.authenticate("alex", "second-demo-password").groups == ("WFM Agents",)
    assert seeded.authenticate("nina", "second-demo-password").groups == ()  # no application access
    with pytest.raises(AuthenticationFailedError):
        seeded.authenticate("ash", "first-demo-password")  # the old password no longer works
