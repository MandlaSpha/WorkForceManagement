import pytest

from wfm.accounts.models import Role
from wfm.identity import roles
from wfm.identity.config import (
    LdapConfig,
    LocalConfig,
    OidcConfig,
    Provisioning,
    RoleRule,
    parse_providers,
    secret_from_env,
)
from wfm.identity.types import ProviderMisconfiguredError


def rules(*pairs: tuple[str, Role], default: Role | None = None, fold: bool = True) -> Provisioning:
    return Provisioning(
        role_rules=[RoleRule(group=g, role=r) for g, r in pairs],
        default_role=default,
        case_insensitive_groups=fold,
    )


class TestRoleMapping:
    def test_a_matching_group_grants_its_role(self) -> None:
        r = rules(("WFM Planners", Role.PLANNER))
        assert roles.role_for(["WFM Planners"], r) == Role.PLANNER

    def test_most_privileged_role_wins_when_several_match(self) -> None:
        r = rules(("a", Role.AGENT), ("l", Role.LEAD), ("p", Role.PLANNER), ("x", Role.ADMIN))
        assert roles.role_for(["a", "l", "p"], r) == Role.PLANNER
        assert roles.role_for(["a", "l", "p", "x"], r) == Role.ADMIN
        assert roles.role_for(["a", "l"], r) == Role.LEAD

    def test_no_match_and_no_default_means_no_role_not_a_guess(self) -> None:
        assert roles.role_for(["Some Other Group"], rules(("WFM Planners", Role.PLANNER))) is None
        assert roles.role_for([], rules(("WFM Planners", Role.PLANNER))) is None

    def test_no_match_falls_back_to_the_default_role(self) -> None:
        r = rules(("WFM Planners", Role.PLANNER), default=Role.AGENT)
        assert roles.role_for(["unrelated"], r) == Role.AGENT

    def test_a_match_beats_the_default(self) -> None:
        r = rules(("WFM Leads", Role.LEAD), default=Role.AGENT)
        assert roles.role_for(["WFM Leads"], r) == Role.LEAD

    def test_group_names_ignore_case_by_default(self) -> None:
        assert (
            roles.role_for(["wfm planners"], rules(("WFM Planners", Role.PLANNER))) == Role.PLANNER
        )

    def test_case_sensitivity_can_be_switched_on(self) -> None:
        r = rules(("WFM Planners", Role.PLANNER), fold=False)
        assert roles.role_for(["wfm planners"], r) is None
        assert roles.role_for(["WFM Planners"], r) == Role.PLANNER

    def test_every_role_is_ranked_exactly_once(self) -> None:
        assert sorted(roles.PRECEDENCE) == sorted(Role)


LDAP = {
    "kind": "ldap",
    "key": "corp",
    "label": "Company directory",
    "server_uri": "ldaps://dc.example.org",
    "bind_dn": "cn=svc,dc=example,dc=org",
    "bind_password_env": "LDAP_PASSWORD",
    "user_search_base": "ou=people,dc=example,dc=org",
}
OIDC = {
    "kind": "oidc",
    "key": "entra",
    "label": "Microsoft",
    "discovery_url": "https://login.example/.well-known/openid-configuration",
    "client_id": "client",
    "client_secret_env": "OIDC_SECRET",
}


class TestConfiguration:
    def test_local_is_always_present_so_a_broken_sso_setup_is_recoverable(self) -> None:
        providers = parse_providers("")
        assert [p.key for p in providers] == ["local"]
        assert isinstance(providers[0], LocalConfig)

    def test_providers_are_read_from_json_with_local_added_first(self) -> None:
        providers = parse_providers(f"[{__import__('json').dumps(LDAP)}]")
        assert [p.key for p in providers] == ["local", "corp"]
        assert isinstance(providers[1], LdapConfig)

    def test_different_kinds_are_told_apart(self) -> None:
        providers = parse_providers([LDAP, OIDC])
        assert [type(p) for p in providers] == [LocalConfig, LdapConfig, OidcConfig]

    def test_a_misspelt_security_setting_is_an_error_not_silently_ignored(self) -> None:
        bad = {**OIDC, "tennant_id": "oops"}
        with pytest.raises(ProviderMisconfiguredError, match="tennant_id"):
            parse_providers([bad])

    def test_duplicate_keys_are_refused(self) -> None:
        with pytest.raises(ProviderMisconfiguredError, match="unique"):
            parse_providers([OIDC, {**OIDC}])

    def test_invalid_json_is_reported(self) -> None:
        with pytest.raises(ProviderMisconfiguredError, match="not valid JSON"):
            parse_providers("{nope")

    def test_unknown_kind_is_refused(self) -> None:
        with pytest.raises(ProviderMisconfiguredError):
            parse_providers([{"kind": "carrier-pigeon", "key": "x", "label": "x"}])

    @pytest.mark.parametrize("key", ["Has Space", "UPPER", "-lead", "a" * 41, ""])
    def test_keys_must_be_url_safe(self, key: str) -> None:
        with pytest.raises(ProviderMisconfiguredError):
            parse_providers([{**OIDC, "key": key}])

    def test_new_providers_default_to_the_safest_provisioning_policy(self) -> None:
        provider = parse_providers([OIDC])[1]
        assert isinstance(provider, OidcConfig)
        p = provider.provisioning
        assert p.mode == "linked_only"  # nobody is created without a decision
        assert p.default_role is None  # nobody gets a role by default
        assert p.match_existing_by is None  # no account merging
        assert p.trust_attributes is False

    def test_secrets_are_referenced_by_name_never_stored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OIDC_SECRET", "s3cret")
        assert secret_from_env("OIDC_SECRET", what="client secret") == "s3cret"

    def test_a_missing_secret_is_a_deployment_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OIDC_SECRET", raising=False)
        with pytest.raises(ProviderMisconfiguredError, match="OIDC_SECRET"):
            secret_from_env("OIDC_SECRET", what="client secret")

    def test_the_configuration_never_contains_a_secret_value(self) -> None:
        provider = parse_providers([OIDC])[1]
        dumped = provider.model_dump_json()
        assert "client_secret_env" in dumped
        assert "s3cret" not in dumped
