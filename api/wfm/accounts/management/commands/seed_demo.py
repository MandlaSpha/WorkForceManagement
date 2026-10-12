"""Create the demo logins shown in the reference video (planner, lead, agent, admin, plus
executive and customer-ops). Synthetic accounts only: never real people (gap G16).

Refuses to run outside development unless WFM_ALLOW_DEMO_SEED=1, so it cannot be fired
accidentally against a real environment.
"""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from wfm.accounts.models import Role, User
from wfm.audit import services as audit
from wfm.audit.models import ActorType

DEMO_ACCOUNTS: tuple[tuple[str, Role, str], ...] = (
    ("planner", Role.PLANNER, "Pat Planner"),
    ("lead", Role.LEAD, "Lee Lead"),
    ("agent", Role.AGENT, "Alex Agent"),
    ("admin", Role.ADMIN, "Ash Admin"),
    ("executive", Role.EXECUTIVE, "Eli Executive"),
    ("customerops", Role.CUSTOMER_OPS, "Casey Customer-Ops"),
)


class Command(BaseCommand):
    help = "Create synthetic demo users (development only)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--password", default=os.environ.get("WFM_DEMO_PASSWORD", ""))

    def handle(self, *args: Any, **options: Any) -> None:
        if not (settings.DEBUG or os.environ.get("WFM_ALLOW_DEMO_SEED") == "1"):
            raise CommandError("Demo seeding is disabled here (set WFM_ALLOW_DEMO_SEED=1).")
        password = options["password"]
        if len(password) < 12:
            raise CommandError(
                "Pass --password (or WFM_DEMO_PASSWORD) with at least 12 characters."
            )

        created = 0
        with transaction.atomic():
            for username, role, full_name in DEMO_ACCOUNTS:
                first, last = full_name.split(" ", 1)
                user, was_created = User.objects.get_or_create(
                    username=username,
                    defaults={"role": role, "first_name": first, "last_name": last},
                )
                if was_created:
                    user.set_password(password)
                    user.save(update_fields=["password"])
                    created += 1
            audit.record(
                actor=None,
                action="system.seed_demo",
                actor_type=ActorType.SYSTEM,
                reason=f"{created} demo users created",
            )
        self.stdout.write(self.style.SUCCESS(f"{created} demo users created."))
