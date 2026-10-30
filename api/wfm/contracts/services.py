"""Creating customers and contracts and putting queues under them. Writes happen here with the
audit event as the LAST write of the transaction. A contract's service-level target and threshold
are written onto each of its queues (through the telephony service, which audits each change)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from django.db import IntegrityError, transaction

from wfm.accounts.models import Role, User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found
from wfm.telephony import services as telephony
from wfm.telephony.models import Queue

from .models import Contract, ContractQueue, Customer, CustomerAssignment


def _invalid(code: str, detail: str, status: int = 422) -> ApiError:
    return ApiError(status, code, "Invalid request", detail)


def _check(name: str, sl_target_pct: Decimal, sl_threshold_s: int) -> str:
    name = name.strip()
    if not 1 <= len(name) <= 100:
        raise _invalid("contract.name_invalid", "A name is 1 to 100 characters.")
    if not Decimal(0) < sl_target_pct <= Decimal(100):
        raise _invalid(
            "contract.sl_target_invalid", "The service-level target is above 0 and at most 100%."
        )
    if not 1 <= sl_threshold_s <= 600:
        raise _invalid(
            "contract.sl_threshold_invalid", "The service-level threshold is 1 to 600 seconds."
        )
    return name


def _same(a: str, b: str) -> bool:
    try:
        return Decimal(a) == Decimal(b)
    except ArithmeticError:
        return a == b


def create_customer(*, user: User, name: str) -> Customer:
    name = name.strip()
    if not 1 <= len(name) <= 100:
        raise _invalid("customer.name_invalid", "A name is 1 to 100 characters.")
    try:
        with transaction.atomic():
            customer = Customer.objects.create(name=name)
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.CUSTOMER_CREATED,
                entity_type="customer",
                entity_id=str(customer.pk),
            )
    except IntegrityError:
        raise _invalid(
            "customer.name_taken", "There is already a customer with that name.", 409
        ) from None
    return customer


def _members(user: User, contract: Contract, queue_ids: Sequence[int]) -> list[Queue]:
    """Put exactly these queues under the contract; each queue is in at most one contract."""
    queues = list(Queue.objects.for_user(user).filter(pk__in=set(queue_ids)).order_by("name"))
    if len(queues) != len(set(queue_ids)):
        raise _invalid("contract.queue_unknown", "A queue in the list does not exist.")
    clash = ContractQueue.objects.filter(queue__in=queues).exclude(contract=contract)
    if clash.exists():
        raise _invalid(
            "contract.queue_taken", "A queue in the list is already under another contract.", 409
        )
    ContractQueue.objects.filter(contract=contract).exclude(queue__in=queues).delete()
    for queue in queues:
        ContractQueue.objects.get_or_create(contract=contract, queue=queue)
    return queues


def _hold_to_contract(user: User, contract: Contract, queues: list[Queue]) -> None:
    """Write the contract's target and threshold onto its queues (only where they differ)."""
    for queue in queues:
        if (
            Decimal(str(queue.sl_target_pct)) != contract.sl_target_pct
            or queue.sl_threshold_s != contract.sl_threshold_s
        ):
            telephony.set_queue_service_level(
                user=user,
                queue_id=queue.pk,
                sl_target_pct=contract.sl_target_pct,
                sl_threshold_s=contract.sl_threshold_s,
            )


def create_contract(
    *,
    user: User,
    customer_id: int,
    name: str,
    sl_target_pct: Decimal,
    sl_threshold_s: int,
    queue_ids: Sequence[int] = (),
) -> Contract:
    name = _check(name, sl_target_pct, sl_threshold_s)
    try:
        with transaction.atomic():
            customer = Customer.objects.for_user(user).filter(pk=customer_id).first()
            if customer is None:
                raise not_found("No such customer.")
            contract = Contract.objects.create(
                customer=customer,
                name=name,
                sl_target_pct=sl_target_pct,
                sl_threshold_s=sl_threshold_s,
            )
            queues = _members(user, contract, queue_ids)
            _hold_to_contract(user, contract, queues)
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.CONTRACT_CREATED,
                entity_type="contract",
                entity_id=str(contract.pk),
                changes=[
                    audit.FieldChange(
                        "contract", str(contract.pk), "sl_target_pct", None, str(sl_target_pct)
                    ),
                    audit.FieldChange(
                        "contract",
                        str(contract.pk),
                        "queues",
                        None,
                        ", ".join(q.name for q in queues),
                    ),
                ],
            )
    except IntegrityError:
        raise _invalid(
            "contract.name_taken", "That customer already has a contract with that name.", 409
        ) from None
    return contract


def update_contract(
    *,
    user: User,
    contract_id: int,
    name: str,
    sl_target_pct: Decimal,
    sl_threshold_s: int,
    active: bool,
    queue_ids: Sequence[int],
) -> Contract:
    name = _check(name, sl_target_pct, sl_threshold_s)
    try:
        with transaction.atomic():
            contract: Contract | None = (
                Contract.objects.select_for_update(no_key=True)
                .for_user(user)
                .filter(pk=contract_id)
                .first()
            )
            if contract is None:
                raise not_found("No such contract.")
            before_queues = sorted(
                ContractQueue.objects.filter(contract=contract).values_list(
                    "queue__name", flat=True
                )
            )
            before = {
                "name": contract.name,
                "sl_target_pct": str(contract.sl_target_pct),
                "sl_threshold_s": str(contract.sl_threshold_s),
                "active": str(contract.active),
            }
            contract.name, contract.sl_target_pct = name, sl_target_pct
            contract.sl_threshold_s, contract.active = sl_threshold_s, active
            contract.save()
            queues = _members(user, contract, queue_ids)
            _hold_to_contract(user, contract, queues)
            after = {
                "name": contract.name,
                "sl_target_pct": str(contract.sl_target_pct),
                "sl_threshold_s": str(contract.sl_threshold_s),
                "active": str(contract.active),
            }
            changes = [
                audit.FieldChange("contract", str(contract.pk), key, before[key], after[key])
                for key in before
                if not _same(before[key], after[key])
            ]
            now_queues = sorted(q.name for q in queues)
            if before_queues != now_queues:
                changes.append(
                    audit.FieldChange(
                        "contract",
                        str(contract.pk),
                        "queues",
                        ", ".join(before_queues),
                        ", ".join(now_queues),
                    )
                )
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.CONTRACT_CHANGED,
                entity_type="contract",
                entity_id=str(contract.pk),
                changes=changes,
            )
    except IntegrityError:
        raise _invalid(
            "contract.name_taken", "That customer already has a contract with that name.", 409
        ) from None
    return contract


def set_assignees(*, user: User, customer_id: int, user_ids: Sequence[int]) -> list[User]:
    """Replace the customer operations managers who look after this customer. Only active
    accounts with that role may be assigned. The trail holds counts and ids, never names."""
    wanted = set(user_ids)
    with transaction.atomic():
        customer = (
            Customer.objects.select_for_update(no_key=True)
            .for_user(user)
            .filter(pk=customer_id)
            .first()
        )
        if customer is None:
            raise not_found("No such customer.")
        people = list(
            User.objects.filter(pk__in=wanted, role=Role.CUSTOMER_OPS, is_active=True).order_by(
                "username"
            )
        )
        if len(people) != len(wanted):
            raise _invalid(
                "customer.assignee_invalid",
                "Each person must be an active customer operations manager.",
            )
        before = set(
            CustomerAssignment.objects.filter(customer=customer).values_list("user_id", flat=True)
        )
        CustomerAssignment.objects.filter(customer=customer).exclude(user__in=people).delete()
        for person in people:
            CustomerAssignment.objects.get_or_create(customer=customer, user=person)
        if before != wanted:
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.CUSTOMER_ASSIGNED,
                entity_type="customer",
                entity_id=str(customer.pk),
                changes=[
                    audit.FieldChange(
                        "customer",
                        str(customer.pk),
                        "assignees",
                        ",".join(map(str, sorted(before))),
                        ",".join(map(str, sorted(wanted))),
                    )
                ],
            )
    return people
