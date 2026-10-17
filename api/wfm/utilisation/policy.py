"""Who may do what with utilisation, cost and workload balance (UTL-01, UTL-02, WLB-01)."""

from __future__ import annotations

from wfm.accounts.models import Role
from wfm.overtime.policy import COST_ROLES as PAY_VISIBLE_ROLES

# Utilisation of a team, customer or contract is an aggregate; a lead sees only their own team.
GROUP_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS, Role.LEAD})
# A row for each named person, in employee-number order and never ranked: the people who plan or
# lead them. Peers (agents) see none; executives and customer operations see groups only.
PERSON_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.LEAD})
# Cost is a pay figure: only those who approve overtime see it (never agents or executives).
COST_ROLES = PAY_VISIBLE_ROLES
# The utilisation target and the contract revenue are the customer's commercial terms.
TERMS_WRITE_ROLES = frozenset({Role.ADMIN})
# Balance suggestions name people on a roster: planners and admins, and leads for their own team.
BALANCE_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.LEAD})

DEFAULT_TARGET_PCT = 75  # an assumption until an admin sets the contract's own (DAT-10)
