"""Administering users (CFG-04): create, change role, switch off, unlock, reset a password, and
change your own. The customer's admin does this; a role handed down by an identity provider's
group mapping cannot be edited here (AUTH-06). Writes happen here with the audit event as the LAST
write of the transaction. No password is ever logged or audited."""

from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found

from .models import Role, RoleSource, User


def _refuse(status: int, code: str, detail: str) -> ApiError:
    return ApiError(status, code, "User change refused", detail)


def _password_problem(password: str, user: User | None = None) -> None:
    try:
        validate_password(password, user)
    except ValidationError as problem:
        raise _refuse(422, "password.too_weak", " ".join(problem.messages)) from None


def _locked_user(user_id: int) -> User:
    found: User | None = User.objects.select_for_update(no_key=True).filter(pk=user_id).first()
    if found is None:
        raise not_found("No such user.")
    return found


def create_user(
    *,
    actor: User,
    username: str,
    first_name: str,
    last_name: str,
    role: str,
    password: str,
) -> User:
    """A local account with a temporary password the person must change at first sign-in."""
    username = username.strip()
    if not 3 <= len(username) <= 150 or " " in username:
        raise _refuse(
            422, "user.username_invalid", "A username is 3 to 150 characters with no spaces."
        )
    if role not in Role.values:
        raise _refuse(422, "user.role_invalid", "Unknown role.")
    candidate = User(username=username, first_name=first_name.strip(), last_name=last_name.strip())
    _password_problem(password, candidate)
    try:
        with transaction.atomic():
            user = User(
                username=username,
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                role=role,
                role_source=RoleSource.LOCAL,
                must_change_password=True,
            )
            user.set_password(password)
            user.save()
            audit.record(  # last write of the transaction
                actor=actor,
                action=Action.USER_CREATED,
                entity_type="user",
                entity_id=str(user.pk),
                changes=[audit.FieldChange("user", str(user.pk), "role", None, role)],
            )
    except IntegrityError:
        raise _refuse(409, "user.username_taken", "That username is already used.") from None
    return user


def set_role(*, actor: User, user_id: int, role: str) -> User:
    if role not in Role.values:
        raise _refuse(422, "user.role_invalid", "Unknown role.")
    with transaction.atomic():
        user = _locked_user(user_id)
        if user.role_source == RoleSource.DIRECTORY:
            raise _refuse(
                409,
                "user.role_from_directory",
                "This role comes from the identity provider's groups. Change it there.",
            )
        # Only an admin gets here, and an admin cannot change their own role or switch off their own
        # account, so there is always at least one active admin: the person doing it.
        if user.pk == actor.pk:
            raise _refuse(409, "user.own_role", "Ask another admin to change your own role.")
        was, user.role = user.role, role
        user.save(update_fields=["role"])
        audit.record(  # last write of the transaction
            actor=actor,
            action=Action.USER_ROLE_SET,
            entity_type="user",
            entity_id=str(user.pk),
            changes=[audit.FieldChange("user", str(user.pk), "role", was, role)],
        )
    return user


def set_active(*, actor: User, user_id: int, active: bool) -> User:
    """Switch an account off (they can no longer sign in; their history stays) or back on."""
    with transaction.atomic():
        user = _locked_user(user_id)
        if user.pk == actor.pk and not active:
            raise _refuse(409, "user.own_account", "You cannot switch off your own account.")
        was, user.is_active = user.is_active, active
        user.save(update_fields=["is_active"])
        audit.record(  # last write of the transaction
            actor=actor,
            action=Action.USER_ACTIVE_SET,
            entity_type="user",
            entity_id=str(user.pk),
            changes=[audit.FieldChange("user", str(user.pk), "active", str(was), str(active))],
        )
    return user


def unlock(*, actor: User, user_id: int) -> User:
    with transaction.atomic():
        user = _locked_user(user_id)
        user.failed_login_count, user.locked_until = 0, None
        user.save(update_fields=["failed_login_count", "locked_until"])
        audit.record(  # last write of the transaction
            actor=actor,
            action=Action.USER_UNLOCKED,
            entity_type="user",
            entity_id=str(user.pk),
        )
    return user


def reset_password(*, actor: User, user_id: int, password: str) -> User:
    """Give a local account a new temporary password; they must change it at next sign-in. An
    account that signs in through a provider has no password here to reset."""
    with transaction.atomic():
        user = _locked_user(user_id)
        if not user.has_usable_password():
            raise _refuse(
                409,
                "user.no_local_password",
                "This person signs in through the identity provider; there is no password here.",
            )
        _password_problem(password, user)
        user.set_password(password)
        user.must_change_password = True
        user.failed_login_count, user.locked_until = 0, None
        user.save(
            update_fields=["password", "must_change_password", "failed_login_count", "locked_until"]
        )
        audit.record(  # last write of the transaction
            actor=actor,
            action=Action.USER_PASSWORD_RESET,
            entity_type="user",
            entity_id=str(user.pk),
        )
    return user


def change_own_password(*, user: User, current: str, new: str) -> User:
    """A person changes their own password (and clears the 'must change' flag)."""
    with transaction.atomic():
        locked = _locked_user(user.pk)
        if not locked.has_usable_password():
            raise _refuse(
                409, "user.no_local_password", "You sign in through the identity provider."
            )
        if not locked.check_password(current):
            raise _refuse(422, "password.wrong", "That is not your current password.")
        if current == new:
            raise _refuse(
                422, "password.unchanged", "Choose a password you have not used just now."
            )
        _password_problem(new, locked)
        locked.set_password(new)
        locked.must_change_password = False
        locked.save(update_fields=["password", "must_change_password"])
        audit.record(  # last write of the transaction
            actor=locked,
            action=Action.USER_PASSWORD_CHANGED,
            entity_type="user",
            entity_id=str(locked.pk),
        )
    return locked
