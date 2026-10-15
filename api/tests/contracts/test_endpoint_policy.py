"""Contract tests that cover EVERY API operation, so a new endpoint cannot ship without a role
policy (CLAUDE.md hard rule; tech spec section 7 role-leak tests).

1. Each operation is either on the explicit public allow-list or declares RoleSessionAuth.
2. Each protected operation is exercised as anonymous and as every role: 401 for anonymous,
   403 (plus an ACCESS_DENIED audit event) for a role outside its allow-list, and never 401/403
   for an allowed role.

Path parameters are filled with a sample id that matches no record. Authentication and the role
check run before the record is looked up, so a refused role gets 403 and an allowed role gets
something other than 401/403 (usually 404). Tests with real records belong to each module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

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
    feature: str | None = None  # the sellable feature it belongs to, or core

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
                feature = str(auths[0].feature) if auths else None
                for method in operation.methods:
                    ops.append(Operation(method, full_path, roles, feature))
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


SAMPLE_ID = "00000000-0000-4000-8000-000000000000"


def request(client: Client, op: Operation):
    path = re.sub(r"\{[^}]+\}", SAMPLE_ID, op.path)
    send = getattr(client, op.method.lower())  # the real method: PUT and DELETE are covered too
    if op.method in {"GET", "DELETE"}:
        return send(path)
    return send(path, content_type="application/json", data={})


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


# --- the feature switch (FEAT-01) -------------------------------------------------------------


def test_no_protected_operation_sits_outside_the_feature_switch() -> None:
    # RoleSessionAuth cannot be built without a feature, so this is the belt to that brace.
    assert all(op.feature for op in PROTECTED), [op.id for op in PROTECTED if not op.feature]


FEATURE_OPS = [op for op in PROTECTED if op.feature != "core"]
CORE_OPS = [op for op in PROTECTED if op.feature == "core"]


def allowed_client(op: Operation) -> Client:
    role = next(iter(op.roles)) if op.roles else Role.PLANNER
    user = User.objects.create_user(username="allowed", password="x", role=role)
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.parametrize("op", FEATURE_OPS, ids=lambda op: op.id)
def test_every_feature_operation_is_refused_when_its_feature_is_off(
    op: Operation, settings: Any
) -> None:
    settings.WFM_FEATURES = "none"
    # A role that is allowed on the operation: the refusal must come from the switch alone.
    response = request(allowed_client(op), op)

    assert response.status_code == 403, f"{op.id} must be refused when {op.feature} is off"
    assert response.json()["code"] == "feature.disabled"


@pytest.mark.parametrize("op", CORE_OPS, ids=lambda op: op.id)
def test_core_operations_work_with_every_feature_off(op: Operation, settings: Any) -> None:
    settings.WFM_FEATURES = "none"
    assert request(allowed_client(op), op).status_code not in {401, 403}


# Which sellable feature each module's routes must belong to. Without this a route could be marked
# "core" (always on) and slip outside the licence switch while still passing the other tests.
MODULE_FEATURE = {
    "/api/v1/telephony": "telephony",
    "/api/v1/forecasting": "forecasting",
    "/api/v1/scheduling": "scheduling",
    "/api/v1/capacity": "capacity",
    "/api/v1/contracts": "capacity",
    "/api/v1/service-desk": "service_desk",
    "/api/v1/people": "people",
}


@pytest.mark.parametrize("op", PROTECTED, ids=lambda op: op.id)
def test_each_module_belongs_to_its_own_feature(op: Operation) -> None:
    for prefix, feature in MODULE_FEATURE.items():
        if op.path.startswith(prefix + "/"):
            assert op.feature == feature, (
                f"{op.id} must be in the {feature} feature, not {op.feature}: "
                "otherwise switching the feature off would not switch it off"
            )
