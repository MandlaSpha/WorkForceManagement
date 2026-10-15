"""Who may do what with customers and contracts."""

from __future__ import annotations

from wfm.accounts.models import Role

# Customers and contracts are commercial facts about queues, read by whoever plans or reports on
# service; the planner and customer operations read, and leads see what their queues are held to.
READ_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS, Role.LEAD})
# What a contract promises is set by the customer's admin.
WRITE_ROLES = frozenset({Role.ADMIN})
