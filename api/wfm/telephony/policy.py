"""Who may do what with call data. One place, so the model scoping and the endpoint role lists
cannot drift apart."""

from __future__ import annotations

from wfm.accounts.models import Role

# Service figures are aggregates (counts and averages per queue), never a person.
AGGREGATE_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.LEAD, Role.EXECUTIVE})

# Importing data changes what everyone sees, so it is narrower than reading it.
IMPORT_ROLES = frozenset({Role.ADMIN, Role.PLANNER})

# Customer operations managers may open the screens, but see only their own contracts' queues
# once contracts exist (requirement CAP-04). Until then the scoping returns none rather than all.
VIEW_ROLES = AGGREGATE_ROLES | {Role.CUSTOMER_OPS}
