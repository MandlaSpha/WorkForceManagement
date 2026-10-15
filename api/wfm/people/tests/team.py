"""A team for the tests: the `u-lead` login as an employee who manages the given people."""

from __future__ import annotations

from wfm.accounts.models import Role, User
from wfm.scheduling.models import Employee
from wfm.scheduling.tests.helpers import person


def lead_of(*employees: Employee, emp_no: str = "L001") -> Employee:
    user, _ = User.objects.get_or_create(username="u-lead", defaults={"role": Role.LEAD})
    lead = Employee.objects.filter(user=user).first() or person(emp_no, user=user)
    for employee in employees:
        employee.manager = lead
        employee.save(update_fields=["manager"])
    return lead
