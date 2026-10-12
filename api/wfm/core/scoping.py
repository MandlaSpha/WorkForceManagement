"""Role scoping. User-facing reads start from `Model.objects.for_user(user)` (code architecture
section 3.4). A model that forgets to define its scope fails loudly instead of leaking rows."""

from __future__ import annotations

from typing import Any, Self

from django.db import models


class ScopedQuerySet(models.QuerySet[Any]):
    def for_user(self, user: Any) -> Self:
        raise NotImplementedError(
            f"{type(self).__name__} must define for_user(): which rows may this user see?"
        )


class ScopedManager(models.Manager[Any].from_queryset(ScopedQuerySet)):  # type: ignore[misc]
    pass
