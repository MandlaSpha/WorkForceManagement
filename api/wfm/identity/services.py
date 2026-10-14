"""The one place a sign-in through an identity provider becomes an application session.

Whatever the provider (LDAP, OIDC, a future SAML adapter), it hands over an `Identity`; this module
links it to a user, creates the user on first sign-in if the provider's policy allows, sets the
role from the provider's group mapping, signs the user in and audits every outcome. Keeping this in
one place is what makes the security rules (AUTH-05 to AUTH-07, AUTH-11) true for every provider.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from django.contrib import auth
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from wfm.accounts.models import Role, RoleSource, User
from wfm.audit import services as audit
from wfm.audit.models import Action, Outcome
from wfm.core import request_context

from . import roles
from .config import LdapConfig, OidcConfig
from .models import IdentityLink
from .types import AuthenticationFailedError, Identity

ModelBackend = "django.contrib.auth.backends.ModelBackend"
_USERNAME_UNSAFE = re.compile(r"[^\w.@+-]")

Provider = LdapConfig | OidcConfig


@dataclass
class _Outcome:
    user: User | None = None
    denied: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)


def complete_login(*, request: HttpRequest, provider: Provider, identity: Identity) -> User:
    """Turn a provider's identity into a signed-in user, or raise AuthenticationFailedError.

    A refusal must still be audited, so the transaction commits first and the exception is raised
    after it closes (raising inside would roll the audit event back). A refusal also creates no
    user and no link: every check runs before the first row is written."""
    with transaction.atomic():
        outcome = _complete(request=request, provider=provider, identity=identity)
    if outcome.denied or outcome.user is None:
        raise AuthenticationFailedError(outcome.denied or "unknown")
    return outcome.user


def _complete(*, request: HttpRequest, provider: Provider, identity: Identity) -> _Outcome:
    out = _Outcome()
    policy = provider.provisioning

    def deny(reason: str, actor: User | None = None) -> _Outcome:
        out.denied = reason
        out.events.append(
            {
                "actor": actor,
                "action": Action.SSO_DENIED,
                "outcome": Outcome.DENIED,
                "reason": f"{provider.key}:{reason}",
            }
        )
        _write(out)
        return out

    link = (
        IdentityLink.objects.select_related("user")
        .select_for_update(no_key=True)
        .filter(provider=provider.key, subject=identity.subject)
        .first()
    )
    user: User | None = link.user if link else None
    matched = False
    if user is None:
        found = _match_existing(provider, identity)
        if found == "ambiguous":
            return deny("ambiguous_match")
        if isinstance(found, User):
            if IdentityLink.objects.filter(provider=provider.key, user=found).exists():
                # the account already belongs to a different identity at this provider
                return deny("conflicting_link", actor=found)
            user, matched = found, True
    creating = user is None and policy.mode == "auto"
    if user is None and not creating:
        return deny("not_provisioned")
    if user is not None and not user.is_active:
        return deny("inactive", actor=user)

    # Decide the role before writing anything, so a refusal leaves no half-created user behind.
    granted: Role | None = None
    if policy.manage_roles or creating:
        granted = roles.role_for(identity.groups, policy)
        if granted is None:
            return deny("no_role", actor=user)

    if creating:
        if granted is None:  # unreachable: creating a user required a granted role above
            raise RuntimeError("provisioning a user without a role")
        user = _create_user(provider, identity, granted)
        out.events.append(
            {
                "actor": user,
                "action": Action.IDENTITY_PROVISIONED,
                "reason": f"{provider.key}; role={granted}",
                "entity_type": "user",
                "entity_id": str(user.pk),
            }
        )
    if user is None:  # unreachable: either found, matched or created above
        raise RuntimeError("no user to sign in")
    if link is None:
        link = IdentityLink.objects.create(
            user=user, provider=provider.key, subject=identity.subject
        )
        if matched:
            out.events.append(
                {
                    "actor": user,
                    "action": Action.IDENTITY_LINKED,
                    "reason": provider.key,
                    "entity_type": "user",
                    "entity_id": str(user.pk),
                }
            )
    if granted is not None and not creating:
        _apply_role(out, user, granted, provider)

    _refresh_profile(user, identity, trusted=policy.trust_attributes)
    link.last_login_at = timezone.now()
    link.save(update_fields=["last_login_at"])

    auth.login(request, user, backend=ModelBackend)  # rotates the session key
    request_context.refresh_session(request.session.session_key)
    out.user = user
    out.events.append(
        {"actor": user, "action": Action.SSO_LOGIN, "reason": f"provider={provider.key}"}
    )
    _write(out)  # last write of the transaction: see audit.services
    return out


def _match_existing(provider: Provider, identity: Identity) -> User | str | None:
    """An existing user this identity may be linked to, "ambiguous", or None.

    Matching on a name or email is only safe when the provider is trusted to control it, and, for
    email, when the address is verified; otherwise anyone who can set that attribute at the provider
    could take over the matching account."""
    policy = provider.provisioning
    if not policy.match_existing_by or not policy.trust_attributes:
        return None
    if policy.match_existing_by == "email":
        if not identity.email or not identity.email_verified:
            return None
        query = Q(email__iexact=identity.email)
    else:
        if not identity.username:
            return None
        query = Q(username__iexact=identity.username)
    found = list(User.objects.select_for_update(no_key=True).filter(query)[:2])
    if len(found) > 1:
        return "ambiguous"
    return found[0] if found else None


def _create_user(provider: Provider, identity: Identity, role: Role) -> User:
    base = _USERNAME_UNSAFE.sub("", identity.username.strip().lower())[:140] or "user"
    username, n = base, 1
    while User.objects.filter(username__iexact=username).exists():
        username = f"{base[:130]}.{provider.key}" if n == 1 else f"{base[:125]}.{provider.key}{n}"
        n += 1
    first, _, last = identity.display_name.partition(" ")
    managed = provider.provisioning.manage_roles
    user = User(
        username=username,
        first_name=first[:150],
        last_name=last[:150],
        email=identity.email if provider.provisioning.trust_attributes else "",
        role=role,
        role_source=RoleSource.DIRECTORY if managed else RoleSource.LOCAL,
    )
    user.set_unusable_password()  # directory users never sign in with a local password
    user.save()
    return user


def _apply_role(out: _Outcome, user: User, granted: Role, provider: Provider) -> None:
    """Make the user's role match the directory's, auditing a change with its old and new value."""
    source = RoleSource.DIRECTORY if provider.provisioning.manage_roles else RoleSource.LOCAL
    if user.role == granted and user.role_source == source:
        return
    old = user.role
    user.role, user.role_source = granted, source
    user.save(update_fields=["role", "role_source"])
    if old != granted:
        out.events.append(
            {
                "actor": user,
                "action": Action.ROLE_CHANGED,
                "reason": provider.key,
                "entity_type": "user",
                "entity_id": str(user.pk),
                "changes": [audit.FieldChange("user", str(user.pk), "role", old, str(granted))],
            }
        )


def _refresh_profile(user: User, identity: Identity, *, trusted: bool) -> None:
    fields: list[str] = []
    if identity.display_name:
        first, _, last = identity.display_name.partition(" ")
        if (user.first_name, user.last_name) != (first[:150], last[:150]):
            user.first_name, user.last_name = first[:150], last[:150]
            fields += ["first_name", "last_name"]
    if trusted and identity.email and user.email != identity.email:
        user.email = identity.email
        fields.append("email")
    if fields:
        user.save(update_fields=fields)


def _write(out: _Outcome) -> None:
    for event in out.events:
        audit.record(**event)
    out.events.clear()
