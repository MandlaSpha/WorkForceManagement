"""Who may do what with service desk work."""

from __future__ import annotations

from wfm.accounts.models import Role

# Customer operations read the workload (it is how their contracts are staffed); planners and
# admins also bring work in and set the productive time.
READ_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.CUSTOMER_OPS})
WRITE_ROLES = frozenset({Role.ADMIN, Role.PLANNER})
