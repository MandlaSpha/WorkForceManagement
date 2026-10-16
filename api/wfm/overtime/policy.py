"""Who may do what with overtime and the pay it is priced from."""

from __future__ import annotations

from wfm.accounts.models import Role

# A lead asks for overtime for their own team; planners and admins for anybody.
REQUEST_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.LEAD})
# Somebody other than the person it is for decides it (never their own).
DECIDE_ROLES = frozenset({Role.ADMIN, Role.PLANNER})
# See everybody's requests.
ALL_SCOPE_ROLES = frozenset({Role.ADMIN, Role.PLANNER})
# What it costs in rands is a pay figure: only those who approve it see it.
COST_ROLES = frozenset({Role.ADMIN, Role.PLANNER})
# Salaries are payroll data: only the customer's admin sets them, and nobody reads one back.
PAY_ROLES = frozenset({Role.ADMIN})
# Overtime is a pay-related screen: agents are told of the outcome but have no screen for it.
READ_ROLES = REQUEST_ROLES
