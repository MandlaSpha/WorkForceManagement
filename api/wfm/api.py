"""The single NinjaAPI instance. Routers from each module are mounted here."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI

from wfm.accounts.api import router as auth_router
from wfm.core.api import router as system_router
from wfm.core.errors import ApiError, problem_response

api = NinjaAPI(
    title="Gijima WFM API",
    version="1.0.0",
    urls_namespace="api-v1",
    docs_url="/docs",
)


@api.exception_handler(ApiError)
def handle_api_error(request: HttpRequest, exc: ApiError) -> HttpResponse:
    return problem_response(request, exc)


api.add_router("/auth", auth_router)
api.add_router("/system", system_router)
