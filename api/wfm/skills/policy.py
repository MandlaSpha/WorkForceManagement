"""Who may do what with credentials, queue requirements, skill gaps and wellbeing prompts."""

from __future__ import annotations

from wfm.accounts.models import Role

# Edit a person's credentials and a queue's requirements.
WRITE_ROLES = frozenset({Role.ADMIN, Role.PLANNER})
ALL_SCOPE_ROLES = WRITE_ROLES
TEAM_ROLES = frozenset({Role.LEAD})
# Credentials: planners and admins see everybody, a lead their team, an agent only their own.
CREDENTIAL_READ_ROLES = ALL_SCOPE_ROLES | TEAM_ROLES | frozenset({Role.AGENT})
REQUIREMENT_READ_ROLES = ALL_SCOPE_ROLES | TEAM_ROLES
# Skill gaps are about a queue's roster, so they belong to the people who build it.
GAP_ROLES = WRITE_ROLES
# Wellbeing prompts: the lead of the team, and planners and admins. Never peers or the person.
WELLBEING_ROLES = ALL_SCOPE_ROLES | TEAM_ROLES

MAX_CREDENTIALS = 40
MAX_REQUIREMENTS = 20
MAX_GAP_DAYS = 31
