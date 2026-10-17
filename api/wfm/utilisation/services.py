"""Setting a contract's utilisation target and monthly revenue. The audit event is the LAST write.
The revenue is a commercial figure: the audit trail records only that one is on file."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.contracts.models import Contract
from wfm.core.errors import ApiError, not_found

from .models import ContractTerms
from .policy import DEFAULT_TARGET_PCT, TERMS_WRITE_ROLES


def set_terms(
    *,
    user: User,
    contract_id: int,
    utilisation_target_pct: Decimal,
    monthly_revenue_zar: Decimal | None,
) -> ContractTerms:
    if user.role not in TERMS_WRITE_ROLES:
        raise not_found("No such contract.")
    if not Decimal(0) < utilisation_target_pct <= Decimal(100):
        raise ApiError(
            422,
            "utilisation.target_invalid",
            "Invalid request",
            "The utilisation target is above 0 and at most 100%.",
        )
    if monthly_revenue_zar is not None and monthly_revenue_zar < 0:
        raise ApiError(
            422,
            "utilisation.revenue_invalid",
            "Invalid request",
            "Revenue cannot be negative.",
        )
    with transaction.atomic():
        contract = Contract.objects.for_user(user).filter(pk=contract_id).first()
        if contract is None:
            raise not_found("No such contract.")
        existing = (
            ContractTerms.objects.select_for_update(no_key=True).filter(contract=contract).first()
        )
        before_target = (
            str(existing.utilisation_target_pct) if existing else str(DEFAULT_TARGET_PCT)
        )
        before_revenue = (
            "on file" if existing and existing.monthly_revenue_zar is not None else "none"
        )
        terms, _ = ContractTerms.objects.update_or_create(
            contract=contract,
            defaults={
                "utilisation_target_pct": utilisation_target_pct,
                "monthly_revenue_zar": monthly_revenue_zar,
                "updated_by": user,
            },
        )
        changes = [
            audit.FieldChange(
                "contract_terms",
                str(contract.pk),
                "utilisation_target_pct",
                before_target,
                str(terms.utilisation_target_pct),
            ),
            audit.FieldChange(
                "contract_terms",
                str(contract.pk),
                "monthly_revenue",
                before_revenue,
                "on file" if terms.monthly_revenue_zar is not None else "none",
            ),
        ]
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.UTILISATION_TERMS_CHANGED,
            entity_type="contract",
            entity_id=str(contract.pk),
            changes=changes,
        )
    return terms
