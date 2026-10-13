"""Mapping directory groups to application roles (requirement AUTH-06). Pure functions."""

from __future__ import annotations

from collections.abc import Iterable

from wfm.accounts.models import Role

from .config import Provisioning

# When someone belongs to groups that map to several roles, the most privileged one wins. The
# order is explicit rather than implied by the enum so it can be reviewed and tested.
PRECEDENCE: tuple[Role, ...] = (
    Role.ADMIN,
    Role.PLANNER,
    Role.LEAD,
    Role.CUSTOMER_OPS,
    Role.EXECUTIVE,
    Role.AGENT,
)


def role_for(groups: Iterable[str], rules: Provisioning) -> Role | None:
    """The role the directory grants, or None when no rule matches and there is no default.

    None means "refuse the sign-in": silently falling back to some role would grant access nobody
    decided to grant."""
    fold = rules.case_insensitive_groups
    member_of = {_norm(g, fold) for g in groups}
    granted = {rule.role for rule in rules.role_rules if _norm(rule.group, fold) in member_of}
    for role in PRECEDENCE:
        if role in granted:
            return role
    return rules.default_role


def _norm(group: str, case_insensitive: bool) -> str:
    return group.casefold() if case_insensitive else group
