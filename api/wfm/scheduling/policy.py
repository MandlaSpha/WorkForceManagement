"""Who may do what with shifts, employees and rosters."""

from __future__ import annotations

from wfm.accounts.models import Role

# Leads read the roster; planners and admins build it.
READ_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.LEAD})
ROSTER_WRITE_ROLES = frozenset({Role.ADMIN, Role.PLANNER})
# Whose employee record can be named as somebody's manager: people who can decide leave.
MANAGER_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.LEAD})
EMPLOYEE_WRITE_ROLES = frozenset({Role.ADMIN, Role.PLANNER})
# The shift library is reference data: configuration belongs to the admin (SCH-01, CFG-02).
SHIFT_WRITE_ROLES = frozenset({Role.ADMIN})
