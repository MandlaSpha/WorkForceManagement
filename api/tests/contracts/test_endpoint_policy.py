"""Contract tests that cover EVERY API operation, so a new endpoint cannot ship without a role
policy (CLAUDE.md hard rule; tech spec section 7 role-leak tests).

1. Each operation is either on the explicit public allow-list or declares RoleSessionAuth.
2. Each protected operation is exercised as anonymous and as every role: 401 for anonymous,
   403 (plus an ACCESS_DENIED audit event) for a role outside its allow-list, and never 401/403
   for an allowed role.

Operations with path parameters are not exercised yet: the test fails loudly if one appears, so
whoever adds it must extend this matrix (with real records) instead of silently skipping it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.api import api
from wfm.audit.models import Action, AuditEvent
from wfm.core.permissions import RoleSessionAuth

pytestmark = pytest.mark.django_db

# Endpoints that are intentionally reachable without a session. Adding here needs a reason.
PUBLIC = {
    ("GET", "/api/v1/auth/csrf"),  # issues the CSRF token before anyone can sign in
    ("POST", "/api/v1/auth/login"),  # signing in; CSRF-protected explicitly
    ("GET", "/api/v1/auth/providers"),  # the login page must know which methods to offer
    ("GET", "/api/v1/auth/sso/{provider_id}/start"),  # begins SSO: the user is not signed in yet
    ("GET", "/api/v1/auth/sso/{provider_id}/callback"),  # the identity provider's return address
}


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    roles: frozenset[Role] | None  # None = public; empty = any signed-in role

    @property
    def id(self) -> str:
        return f"{self.method} {self.path}"


def all_operations() -> list[Operation]:
    ops: list[Operation] = []
    for prefix, router in api._routers:
        for sub_path, view in router.path_operations.items():
            for operation in view.operations:
                full_path = f"/api/v1{prefix}{sub_path}"
                auths = [a for a in operation.auth_callbacks if isinstance(a, RoleSessionAuth)]
                roles = auths[0].roles if auths else None
                for method in operation.methods:
                    ops.append(Operation(method, full_path, roles))
    return ops


OPERATIONS = all_operations()
PROTECTED = [op for op in OPERATIONS if op.roles is not None]


def test_operation_discovery_finds_the_api() -> None:
    assert len(OPERATIONS) >= 4


@pytest.mark.parametrize("op", OPERATIONS, ids=lambda op: op.id)
def test_every_operation_is_public_on_purpose_or_declares_roles(op: Operation) -> None:
    if op.roles is None:
        assert (op.method, op.path) in PUBLIC, (
            f"{op.id} has no role policy. Protect it with RoleSessionAuth(<roles>) "
            "or, if it must be public, add it to PUBLIC with a reason."
        )
    else:
        assert (op.method, op.path) not in PUBLIC, f"{op.id} is listed public but is protected"


@pytest.mark.parametrize("op", OPERATIONS, ids=lambda op: op.id)
def test_no_path_parameters_without_matrix_coverage(op: Operation) -> None:
    # Public routes have no roles to exercise, so a path parameter is fine there.
    assert "{" not in op.path or (op.method, op.path) in PUBLIC, (
        f"{op.id}: extend the role matrix to cover path parameters"
    )


def request(client: Client, op: Operation):
    if op.method == "GET":
        return client.get(op.path)
    return client.post(op.path, content_type="application/json", data={})


@pytest.mark.parametrize("op", PROTECTED, ids=lambda op: op.id)
def test_anonymous_is_refused(op: Operation) -> None:
    assert request(Client(), op).status_code == 401


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("op", PROTECTED, ids=lambda op: op.id)
def test_role_matrix(op: Operation, role: Role) -> None:
    user = User.objects.create_user(username=f"u-{role.value}", password="x", role=role)
    client = Client()
    client.force_login(user)
    allowed = not op.roles or role in op.roles

    response = request(client, op)

    if allowed:
        assert response.status_code not in {401, 403}, f"{role.value} should reach {op.id}"
    else:
        assert response.status_code == 403, f"{role.value} must be refused on {op.id}"
        denied = AuditEvent.objects.filter(action=Action.ACCESS_DENIED, actor_user_id=user.pk)
        assert denied.count() == 1
        assert denied.get().actor_role == role.value
