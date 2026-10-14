"""Who may do what with capacity planning."""

from __future__ import annotations

from wfm.accounts.models import Role

# Capacity is headcount, not people: executives and customer operations read it with the planners.
READ_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS})
# The workforce limits are a contract fact, set by the admin.
WRITE_ROLES = frozenset({Role.ADMIN})
