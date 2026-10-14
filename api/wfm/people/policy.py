"""Who may do what with leave."""

from __future__ import annotations

from wfm.accounts.models import Role

# Everyone who works a roster may have leave of their own.
SELF_ROLES = frozenset({Role.AGENT, Role.LEAD, Role.PLANNER, Role.ADMIN})
# Leads, planners and admins see and decide everyone's requests. (A lead's own team needs the
# employee's manager link, which is not built: until then a lead decides for everyone.)
APPROVE_ROLES = frozenset({Role.LEAD, Role.PLANNER, Role.ADMIN})
# Planners and admins can also apply on someone's behalf (a phone call, a medical certificate).
ON_BEHALF_ROLES = frozenset({Role.PLANNER, Role.ADMIN})
# The entitlements are a policy decision of the customer's admin.
CONFIG_ROLES = frozenset({Role.ADMIN})
