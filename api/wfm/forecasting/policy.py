"""Who may do what with forecasts."""

from __future__ import annotations

from wfm.accounts.models import Role

# The forecast screen is for the people who plan; leads may read it but not change it.
READ_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.LEAD})
WRITE_ROLES = frozenset({Role.ADMIN, Role.PLANNER})
