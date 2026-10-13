"""Fill a development LDAP directory with synthetic people and groups, so sign-in through the
directory can be tried (and tested in a browser) without a real company directory.

Development only, like seed_demo: it refuses to run outside DEBUG unless WFM_ALLOW_DEMO_SEED=1.
Idempotent: existing entries are kept and passwords are reset to the current demo password.
"""

from __future__ import annotations

import os
import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from ldap3 import Connection, Server
from ldap3.core.exceptions import LDAPException

BASE = "dc=example,dc=org"
PEOPLE = f"ou=people,{BASE}"
GROUPS = f"ou=groups,{BASE}"

# uid, display name, group (None = a person with no application access)
PEOPLE_AND_GROUPS: tuple[tuple[str, str, str | None], ...] = (
    ("pat", "Pat Planner", "WFM Planners"),
    ("lee", "Lee Lead", "WFM Leads"),
    ("alex", "Alex Agent", "WFM Agents"),
    ("ash", "Ash Admin", "WFM Admins"),
    ("nina", "Nina Nogroup", None),
)


class Command(BaseCommand):
    help = "Create synthetic users and groups in a development LDAP directory."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--uri", default=os.environ.get("LDAP_URI", "ldap://localhost:3890"))
        parser.add_argument("--admin-dn", default=f"cn=admin,{BASE}")
        parser.add_argument(
            "--wait-s", type=int, default=90, help="How long to wait for the server."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not (settings.DEBUG or os.environ.get("WFM_ALLOW_DEMO_SEED") == "1"):
            raise CommandError("Demo seeding is disabled here (set WFM_ALLOW_DEMO_SEED=1).")
        admin_password = os.environ.get("LDAP_ADMIN_PASSWORD", "")
        demo_password = os.environ.get("WFM_DEMO_PASSWORD", "")
        if not admin_password or len(demo_password) < 12:
            raise CommandError(
                "Set LDAP_ADMIN_PASSWORD and WFM_DEMO_PASSWORD (at least 12 characters)."
            )

        conn = self._connect(options["uri"], options["admin_dn"], admin_password, options["wait_s"])
        try:
            self._add(conn, PEOPLE, ["organizationalUnit"], {"ou": "people"})
            self._add(conn, GROUPS, ["organizationalUnit"], {"ou": "groups"})
            members: dict[str, list[str]] = {}
            for uid, name, group in PEOPLE_AND_GROUPS:
                dn = f"uid={uid},{PEOPLE}"
                self._add(
                    conn,
                    dn,
                    ["inetOrgPerson"],
                    {
                        "uid": uid,
                        "cn": name,
                        "sn": name.split()[-1],
                        "mail": f"{uid}@example.org",
                        "displayName": name,
                        "userPassword": demo_password,
                    },
                )
                # an existing user keeps their entry, but the password follows the current secret
                conn.extend.standard.modify_password(dn, new_password=demo_password)
                if group:
                    members.setdefault(group, []).append(dn)
            for group, dns in members.items():
                self._add(
                    conn, f"cn={group},{GROUPS}", ["groupOfNames"], {"cn": group, "member": dns}
                )
        finally:
            conn.unbind()
        self.stdout.write(self.style.SUCCESS(f"Directory seeded: {len(PEOPLE_AND_GROUPS)} people."))

    @staticmethod
    def _connect(uri: str, dn: str, password: str, wait_s: int) -> Connection:
        """The directory container may still be starting; keep trying for a while."""
        deadline = time.monotonic() + wait_s
        while True:
            try:
                return Connection(Server(uri), user=dn, password=password, auto_bind=True)
            except LDAPException as exc:
                if time.monotonic() > deadline:
                    raise CommandError(f"Directory at {uri} did not come up: {exc}") from exc
                time.sleep(2)

    @staticmethod
    def _add(conn: Connection, dn: str, classes: list[str], attrs: dict[str, object]) -> None:
        if conn.add(dn, classes, attrs):
            return
        if conn.result.get("description") == "entryAlreadyExists":
            return
        raise CommandError(f"Could not create {dn}: {conn.result}")
