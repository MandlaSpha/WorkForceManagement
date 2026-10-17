"""Who may do what with backup teams and the mobilise view (BCP-01)."""

from __future__ import annotations

from wfm.accounts.models import Role

# Planners and admins name the backup teams.
WRITE_ROLES = frozenset({Role.ADMIN, Role.PLANNER})
# A lead reads them (they already read the roster and the employee list). An executive reads the
# numbers only: no names. Agents and customer operations have no part in continuity planning.
NAMED_READ_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.LEAD})
READ_ROLES = NAMED_READ_ROLES | {Role.EXECUTIVE}

DEFAULT_LOST_PCT = 30
