"""Who may do what with attendance and adherence."""

from __future__ import annotations

from wfm.accounts.models import Role

# Load a state file, and see every team's adherence.
IMPORT_ROLES = frozenset({Role.ADMIN, Role.PLANNER})
# A lead sees the adherence of their own team only.
TEAM_ROLES = frozenset({Role.LEAD})
READ_ROLES = IMPORT_ROLES | TEAM_ROLES
# Everyone on a roster sees their own planned-versus-actual day.
SELF_ROLES = frozenset({Role.AGENT, Role.LEAD, Role.PLANNER, Role.ADMIN})

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ROWS = 200_000
DAYS_BACK, DAYS_AHEAD = 92, 1
