from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    AGENT = "agent", "Agent"
    LEAD = "lead", "Team lead"
    PLANNER = "planner", "Planner"
    ADMIN = "admin", "Admin"
    EXECUTIVE = "executive", "Executive"
    CUSTOMER_OPS = "customer_ops", "Customer operations manager"


class RoleSource(models.TextChoices):
    LOCAL = "local", "Managed in the application"
    DIRECTORY = "directory", "Managed by the identity provider"


class User(AbstractUser):
    """Application user. `role` drives every permission and scoping decision."""

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.AGENT)
    role_source = models.CharField(
        max_length=10, choices=RoleSource.choices, default=RoleSource.LOCAL
    )
    """Who decides the role. "directory" means a provider's group mapping sets it at every sign-in
    and the application must not offer to edit it by hand (AUTH-06)."""
    must_change_password = models.BooleanField(default=False)
    """Set when an admin gave the account a temporary password; the person must choose their own."""
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=[r.value for r in Role]),
                name="accounts_user_role_valid",
            ),
        ]
