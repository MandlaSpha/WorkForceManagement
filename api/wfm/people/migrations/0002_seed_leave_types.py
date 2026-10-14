"""The leave types, with South African (BCEA) entitlements as defaults nobody has confirmed.

Annual leave is 21 consecutive days, which is 15 working days; sick leave is 30 days in a
three-year cycle, taken here as 10 a year; family responsibility is 3 days; maternity is 4
consecutive months, about 85 working days (unpaid by the employer; UIF pays). Study and training
follow the employer's policy: the admin sets them.
"""

from decimal import Decimal

from django.db import migrations

TYPES = [
    ("annual", "Annual leave", True, Decimal("15")),
    ("sick", "Sick leave", True, Decimal("10")),
    ("family", "Family responsibility leave", True, Decimal("3")),
    ("study", "Study leave", True, Decimal("5")),
    ("maternity", "Maternity leave", False, Decimal("85")),
    ("training", "Training", True, None),
    ("unpaid", "Unpaid leave", False, None),
]


def add_types(apps, schema_editor):
    LeaveType = apps.get_model("people", "LeaveType")
    for code, name, paid, days in TYPES:
        LeaveType.objects.get_or_create(
            code=code, defaults={"name": name, "paid": paid, "days_per_year": days}
        )


class Migration(migrations.Migration):
    dependencies = [("people", "0001_initial")]
    operations = [migrations.RunPython(add_types, migrations.RunPython.noop)]
