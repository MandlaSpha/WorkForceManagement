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


class User(AbstractUser):
    """Application user. `role` drives every permission and scoping decision."""

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.AGENT)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=[r.value for r in Role]),
                name="accounts_user_role_valid",
            ),
        ]
