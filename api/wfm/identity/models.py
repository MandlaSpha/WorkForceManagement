from __future__ import annotations

from django.conf import settings
from django.db import models


class IdentityLink(models.Model):
    """Ties a user to one identity at one provider: (provider, stable subject). The subject is the
    provider's never-reused id, so renaming someone in the directory cannot detach or hijack the
    account."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="identity_links"
    )
    provider = models.CharField(max_length=40)
    subject = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "subject"], name="identity_link_unique"),
            # one identity per provider per user, so a user cannot be linked twice to one directory
            models.UniqueConstraint(
                fields=["provider", "user"], name="identity_link_one_per_provider"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.subject} -> user {self.user_id}"
