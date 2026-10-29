"""Small, plain-data read for the Copilot (tech spec section 8.2)."""

from __future__ import annotations

from dataclasses import dataclass

from wfm.accounts.models import User

from .models import Contract


@dataclass(frozen=True, slots=True)
class ContractCounts:
    contracts: int
    active: int


def contract_counts(user: User) -> ContractCounts:
    """How many contracts the role may read, and how many are active. Numbers only: no customer
    or contract is named, because a customer operations manager has no link to their own
    customers yet and naming would risk showing someone else's contract."""
    found = Contract.objects.for_user(user)
    return ContractCounts(found.count(), found.filter(active=True).count())
