"""Typed business errors and the RFC 9457 problem-details response (standards section 4)."""

from __future__ import annotations

from dataclasses import dataclass, field

from django.http import HttpRequest, JsonResponse


@dataclass
class ApiError(Exception):
    status: int
    code: str
    title: str
    detail: str = ""
    violations: list[dict[str, str]] = field(default_factory=list)

    def __str__(self) -> str:
        return f"{self.code}: {self.title}"


def unauthorised(detail: str = "Authentication required.") -> ApiError:
    return ApiError(401, "auth.required", "Not authenticated", detail)


def forbidden(detail: str = "Your role may not do this.") -> ApiError:
    return ApiError(403, "auth.forbidden", "Forbidden", detail)


def not_found(detail: str = "Not found.") -> ApiError:
    # Out-of-scope records also surface as 404 so their existence is not revealed.
    return ApiError(404, "resource.not_found", "Not found", detail)


def problem_response(request: HttpRequest, exc: ApiError) -> JsonResponse:
    body: dict[str, object] = {
        "type": f"https://wfm.local/problems/{exc.code}",
        "title": exc.title,
        "status": exc.status,
        "code": exc.code,
    }
    if exc.detail:
        body["detail"] = exc.detail
    if exc.violations:
        body["violations"] = exc.violations
    return JsonResponse(body, status=exc.status, content_type="application/problem+json")
