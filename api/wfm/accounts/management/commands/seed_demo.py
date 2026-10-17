"""Create the demo logins shown in the reference video (planner, lead, agent, admin, plus
executive and customer-ops). Synthetic accounts only: never real people (gap G16).

Refuses to run outside development unless WFM_ALLOW_DEMO_SEED=1, so it cannot be fired
accidentally against a real environment.
"""

from __future__ import annotations

import os
from typing import Any

from django.apps import apps
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

# Two small teams to see swaps and approvals with: Lee Lead leads `agent` and agent2 to agent5;
# Lou Lead leads agent6 to agent10. All are synthetic.
DEMO_TEAM_ACCOUNTS: tuple[tuple[str, Role, str, str], ...] = (
    ("lead2", Role.LEAD, "Lou Lead", ""),
    ("agent2", Role.AGENT, "Blake Agent", "lead"),
    ("agent3", Role.AGENT, "Cam Agent", "lead"),
    ("agent4", Role.AGENT, "Dee Agent", "lead"),
    ("agent5", Role.AGENT, "Eden Agent", "lead"),
    ("agent6", Role.AGENT, "Fran Agent", "lead2"),
    ("agent7", Role.AGENT, "Gus Agent", "lead2"),
    ("agent8", Role.AGENT, "Hal Agent", "lead2"),
    ("agent9", Role.AGENT, "Ira Agent", "lead2"),
    ("agent10", Role.AGENT, "Jo Agent", "lead2"),
)


class Command(BaseCommand):
    help = "Create synthetic demo users (development only)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--password", default=os.environ.get("WFM_DEMO_PASSWORD", ""))
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Also set the password (and clear any lockout) on demo accounts that exist.",
        )

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
            for username, role, full_name in (
                *DEMO_ACCOUNTS,
                *((u, r, n) for u, r, n, _ in DEMO_TEAM_ACCOUNTS),
            ):
                first, last = full_name.split(" ", 1)
                user, was_created = User.objects.get_or_create(
                    username=username,
                    defaults={"role": role, "first_name": first, "last_name": last},
                )
                if was_created:
                    created += 1
                if role in (Role.AGENT, Role.LEAD):
                    # Synthetic employee records for the demo agent and lead, who work the floor:
                    # their own leave and swap screens have somebody to show, and they can swap
                    # shifts with each other (the records name no real person).
                    employee_model = apps.get_model("scheduling", "Employee")
                    employee_model.objects.get_or_create(
                        user=user,
                        defaults={"emp_no": f"DEMO-{username.upper()}", "name": full_name},
                    )
                if was_created or options["reset_passwords"]:
                    user.set_password(password)
                    user.failed_login_count = 0
                    user.locked_until = None
                    user.save(update_fields=["password", "failed_login_count", "locked_until"])
            # The demo lead manages the demo agent, so the lead can decide the agent's leave.
            employee_model = apps.get_model("scheduling", "Employee")
            lead = employee_model.objects.filter(emp_no="DEMO-LEAD").first()
            if lead is not None:
                employee_model.objects.filter(emp_no="DEMO-AGENT").update(manager=lead)
            for username, _, _, boss in DEMO_TEAM_ACCOUNTS:
                if boss:
                    employee_model.objects.filter(emp_no=f"DEMO-{username.upper()}").update(
                        manager=employee_model.objects.filter(emp_no=f"DEMO-{boss.upper()}").first()
                    )
            audit.record(
                actor=None,
                action="system.seed_demo",
                actor_type=ActorType.SYSTEM,
                reason=f"{created} demo users created",
            )
        self.stdout.write(self.style.SUCCESS(f"{created} demo users created."))
