"""Who may do what with imported quality results (QUA-01)."""

from __future__ import annotations

from wfm.accounts.models import Role

# Load a quality file, and see every team's results.
IMPORT_ROLES = frozenset({Role.ADMIN, Role.PLANNER})
# A lead sees the results of their own team, and of themselves.
TEAM_ROLES = frozenset({Role.LEAD})
# Read a team's people one by one: planner, admin, and the lead of the team. Never peers.
REVIEW_ROLES = IMPORT_ROLES | TEAM_ROLES
# Everyone who is on the employee list sees their OWN results (agents included).
SELF_ROLES = frozenset({Role.AGENT, Role.LEAD, Role.PLANNER, Role.ADMIN})

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20_000
MAX_ERRORS_KEPT = 50
SHOWN_UNMAPPED = 50
DEFAULT_DAYS, MAX_DAYS = 90, 366
