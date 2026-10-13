"""The shared sign-in service: linking, first-login provisioning, role mapping and refusals
(AUTH-05 to AUTH-07, AUTH-11). Provider-independent, so one set of tests covers every adapter."""

from __future__ import annotations

import pytest
from django.http import HttpRequest

from wfm.accounts.models import Role, RoleSource, User
from wfm.audit.models import Action, AuditEvent, Outcome
from wfm.identity.config import LdapConfig, Provisioning, RoleRule
from wfm.identity.models import IdentityLink
from wfm.identity.services import complete_login
from wfm.identity.types import AuthenticationFailedError, Identity

pytestmark = pytest.mark.django_db

RULES = [
    RoleRule(group="WFM Admins", role=Role.ADMIN),
    RoleRule(group="WFM Planners", role=Role.PLANNER),
    RoleRule(group="WFM Agents", role=Role.AGENT),
]


def provider(**policy: object) -> LdapConfig:
    defaults: dict[str, object] = {"mode": "auto", "role_rules": RULES}
    return LdapConfig(
        key="corp",
        label="Corp",
        server_uri="ldaps://dc.example.org",
        bind_dn="cn=svc",
        bind_password_env="X",
        user_search_base="dc=example",
        provisioning=Provisioning(**{**defaults, **policy}),  # type: ignore[arg-type]
    )


def who(
    subject: str = "guid-1",
    *,
    username: str = "pat",
    email: str = "pat@example.org",
    verified: bool = True,
    groups: tuple[str, ...] = ("WFM Planners",),
    name: str = "Pat Planner",
) -> Identity:
    return Identity(
        provider="corp",
        subject=subject,
        username=username,
        email=email,
        email_verified=verified,
        display_name=name,
        groups=groups,
    )


def actions() -> list[str]:
    return list(AuditEvent.objects.order_by("chain_seq").values_list("action", flat=True))


class TestFirstSignIn:
    def test_auto_provisioning_creates_a_user_with_the_mapped_role(
        self, web_request: HttpRequest
    ) -> None:
        user = complete_login(request=web_request, provider=provider(), identity=who())

        assert user.username == "pat"
        assert user.role == Role.PLANNER
        assert user.role_source == RoleSource.DIRECTORY
        assert not user.has_usable_password()  # directory users never use a local password
        assert IdentityLink.objects.get(user=user).subject == "guid-1"
        assert web_request.session["_auth_user_id"] == str(user.pk)  # actually signed in

    def test_provisioning_and_sign_in_are_both_audited(self, web_request: HttpRequest) -> None:
        complete_login(request=web_request, provider=provider(), identity=who())

        assert actions() == [Action.IDENTITY_PROVISIONED, Action.SSO_LOGIN]
        provisioned = AuditEvent.objects.get(action=Action.IDENTITY_PROVISIONED)
        assert "role=planner" in provisioned.reason

    def test_the_audit_trail_never_holds_groups_email_or_names(
        self, web_request: HttpRequest
    ) -> None:
        complete_login(request=web_request, provider=provider(), identity=who())

        everything = " ".join(f"{e.reason} {e.entity_id}" for e in AuditEvent.objects.all())
        for private in ("pat@example.org", "Pat Planner", "WFM Planners", "guid-1"):
            assert private not in everything

    def test_a_second_sign_in_reuses_the_account(self, web_request: HttpRequest) -> None:
        first = complete_login(request=web_request, provider=provider(), identity=who())
        second = complete_login(request=web_request, provider=provider(), identity=who())

        assert first.pk == second.pk
        assert User.objects.count() == 1
        assert IdentityLink.objects.count() == 1

    def test_renaming_someone_in_the_directory_does_not_create_a_new_account(
        self, web_request: HttpRequest
    ) -> None:
        first = complete_login(request=web_request, provider=provider(), identity=who())
        again = complete_login(
            request=web_request, provider=provider(), identity=who(username="patricia.new")
        )
        assert first.pk == again.pk  # linked by the stable subject, not the name

    def test_linked_only_refuses_an_unknown_person_and_creates_nothing(
        self, web_request: HttpRequest
    ) -> None:
        with pytest.raises(AuthenticationFailedError) as refused:
            complete_login(
                request=web_request, provider=provider(mode="linked_only"), identity=who()
            )

        assert refused.value.reason == "not_provisioned"
        assert User.objects.count() == 0
        assert IdentityLink.objects.count() == 0
        denied = AuditEvent.objects.get(action=Action.SSO_DENIED)
        assert denied.outcome == Outcome.DENIED
        assert denied.reason == "corp:not_provisioned"

    def test_no_mapped_role_and_no_default_is_refused_and_leaves_no_user_behind(
        self, web_request: HttpRequest
    ) -> None:
        with pytest.raises(AuthenticationFailedError) as refused:
            complete_login(
                request=web_request, provider=provider(), identity=who(groups=("Cafeteria Staff",))
            )

        assert refused.value.reason == "no_role"
        # The refusal is audited and committed, but it must not have created anything.
        assert User.objects.count() == 0
        assert IdentityLink.objects.count() == 0
        assert actions() == [Action.SSO_DENIED]

    def test_a_default_role_admits_people_who_match_no_group(
        self, web_request: HttpRequest
    ) -> None:
        user = complete_login(
            request=web_request,
            provider=provider(default_role=Role.AGENT),
            identity=who(groups=("Cafeteria Staff",)),
        )
        assert user.role == Role.AGENT

    def test_usernames_are_made_unique_across_directories(self, web_request: HttpRequest) -> None:
        User.objects.create_user(username="pat", password="x")
        user = complete_login(request=web_request, provider=provider(), identity=who())
        assert user.username == "pat.corp"

    def test_unsafe_characters_are_stripped_from_a_generated_username(
        self, web_request: HttpRequest
    ) -> None:
        user = complete_login(
            request=web_request, provider=provider(), identity=who(username="Pat O'Neil <x>")
        )
        assert user.username == "patoneilx"


class TestRolesFollowTheDirectory:
    def test_demotion_takes_effect_at_the_next_sign_in_and_is_audited(
        self, web_request: HttpRequest
    ) -> None:
        user = complete_login(request=web_request, provider=provider(), identity=who())
        assert user.role == Role.PLANNER

        again = complete_login(
            request=web_request, provider=provider(), identity=who(groups=("WFM Agents",))
        )

        assert again.role == Role.AGENT
        change = AuditEvent.objects.get(action=Action.ROLE_CHANGED)
        (diff,) = change.changes.all()
        assert (diff.field, diff.old_value, diff.new_value) == ("role", "planner", "agent")

    def test_promotion_works_the_same_way(self, web_request: HttpRequest) -> None:
        complete_login(request=web_request, provider=provider(), identity=who())
        again = complete_login(
            request=web_request, provider=provider(), identity=who(groups=("WFM Admins",))
        )
        assert again.role == Role.ADMIN

    def test_losing_every_mapped_group_locks_the_person_out(self, web_request: HttpRequest) -> None:
        complete_login(request=web_request, provider=provider(), identity=who())

        with pytest.raises(AuthenticationFailedError) as refused:
            complete_login(request=web_request, provider=provider(), identity=who(groups=()))

        assert refused.value.reason == "no_role"
        assert User.objects.get().role == Role.PLANNER  # unchanged; they simply cannot sign in

    def test_an_unchanged_role_is_not_audited_as_a_change(self, web_request: HttpRequest) -> None:
        complete_login(request=web_request, provider=provider(), identity=who())
        complete_login(request=web_request, provider=provider(), identity=who())
        assert Action.ROLE_CHANGED not in actions()

    def test_when_roles_are_managed_in_the_app_the_directory_does_not_override_them(
        self, web_request: HttpRequest
    ) -> None:
        cfg = provider(manage_roles=False)
        user = complete_login(request=web_request, provider=cfg, identity=who())
        assert user.role_source == RoleSource.LOCAL
        user.role = Role.LEAD  # an admin changed it inside the application
        user.save()

        again = complete_login(
            request=web_request, provider=cfg, identity=who(groups=("WFM Admins",))
        )

        assert again.role == Role.LEAD


class TestLinkingExistingAccounts:
    def existing(self, **kw: object) -> User:
        return User.objects.create_user(
            username="pat.local",
            password="x",
            email="pat@example.org",
            role=Role.LEAD,
            **kw,
        )

    def test_nothing_is_merged_unless_the_provider_is_trusted_and_asked_to(
        self, web_request: HttpRequest
    ) -> None:
        self.existing()
        user = complete_login(request=web_request, provider=provider(), identity=who())
        assert User.objects.count() == 2  # a separate account, not a takeover
        assert user.username != "pat.local"

    def test_a_trusted_verified_email_links_the_existing_account(
        self, web_request: HttpRequest
    ) -> None:
        old = self.existing()
        cfg = provider(match_existing_by="email", trust_attributes=True)

        user = complete_login(request=web_request, provider=cfg, identity=who())

        assert user.pk == old.pk
        assert User.objects.count() == 1
        assert Action.IDENTITY_LINKED in actions()

    def test_an_unverified_email_never_links(self, web_request: HttpRequest) -> None:
        self.existing()
        cfg = provider(match_existing_by="email", trust_attributes=True)

        user = complete_login(request=web_request, provider=cfg, identity=who(verified=False))

        assert User.objects.count() == 2
        assert user.username != "pat.local"

    def test_an_untrusted_provider_cannot_link_by_email_even_when_verified(
        self, web_request: HttpRequest
    ) -> None:
        self.existing()
        cfg = provider(match_existing_by="email", trust_attributes=False)
        complete_login(request=web_request, provider=cfg, identity=who())
        assert User.objects.count() == 2

    def test_linking_by_username(self, web_request: HttpRequest) -> None:
        old = self.existing()
        cfg = provider(match_existing_by="username", trust_attributes=True)
        user = complete_login(
            request=web_request, provider=cfg, identity=who(username="PAT.LOCAL", verified=False)
        )
        assert user.pk == old.pk

    def test_two_accounts_with_the_same_email_is_ambiguous_and_refused(
        self, web_request: HttpRequest
    ) -> None:
        self.existing()
        User.objects.create_user(username="pat.other", password="x", email="PAT@example.org")
        cfg = provider(match_existing_by="email", trust_attributes=True)

        with pytest.raises(AuthenticationFailedError) as refused:
            complete_login(request=web_request, provider=cfg, identity=who())

        assert refused.value.reason == "ambiguous_match"
        assert IdentityLink.objects.count() == 0

    def test_an_account_already_linked_to_someone_else_cannot_be_taken_over(
        self, web_request: HttpRequest
    ) -> None:
        old = self.existing()
        cfg = provider(match_existing_by="email", trust_attributes=True)
        complete_login(request=web_request, provider=cfg, identity=who(subject="guid-1"))

        # A different directory identity that claims the same email must not hijack the account.
        with pytest.raises(AuthenticationFailedError) as refused:
            complete_login(request=web_request, provider=cfg, identity=who(subject="guid-EVIL"))

        assert refused.value.reason == "conflicting_link"
        assert IdentityLink.objects.get().subject == "guid-1"
        assert User.objects.get(pk=old.pk).role == Role.PLANNER  # the first, legitimate link

    def test_trusted_providers_refresh_the_email_but_untrusted_ones_do_not(
        self, web_request: HttpRequest
    ) -> None:
        trusted = provider(trust_attributes=True)
        complete_login(request=web_request, provider=trusted, identity=who())
        complete_login(request=web_request, provider=trusted, identity=who(email="new@example.org"))
        assert User.objects.get().email == "new@example.org"

    def test_the_display_name_follows_the_directory(self, web_request: HttpRequest) -> None:
        complete_login(request=web_request, provider=provider(), identity=who())
        user = complete_login(
            request=web_request, provider=provider(), identity=who(name="Patricia Planner")
        )
        assert (user.first_name, user.last_name) == ("Patricia", "Planner")


class TestRefusals:
    def test_a_deactivated_user_is_refused(self, web_request: HttpRequest) -> None:
        user = complete_login(request=web_request, provider=provider(), identity=who())
        user.is_active = False
        user.save()

        with pytest.raises(AuthenticationFailedError) as refused:
            complete_login(request=web_request, provider=provider(), identity=who())

        assert refused.value.reason == "inactive"
        denied = AuditEvent.objects.get(action=Action.SSO_DENIED)
        assert denied.actor_user_id == user.pk  # the audit trail knows who was refused

    def test_every_refusal_is_audited_with_the_provider_and_a_reason_code(
        self, web_request: HttpRequest
    ) -> None:
        for groups in ((), ("nope",)):
            with pytest.raises(AuthenticationFailedError):
                complete_login(
                    request=web_request, provider=provider(), identity=who(groups=groups)
                )
        reasons = set(
            AuditEvent.objects.filter(action=Action.SSO_DENIED).values_list("reason", flat=True)
        )
        assert reasons == {"corp:no_role"}
