"""The single NinjaAPI instance. Routers from each module are mounted here."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI

from wfm.accounts.api import router as auth_router
from wfm.accounts.user_api import router as users_router
from wfm.attendance.api import router as attendance_router
from wfm.audit.api import router as audit_router
from wfm.capacity.api import router as capacity_router
from wfm.continuity.api import router as continuity_router
from wfm.contracts.api import router as contracts_router
from wfm.core.api import router as system_router
from wfm.core.errors import ApiError, problem_response
from wfm.forecasting.api import router as forecasting_router
from wfm.identity.api import router as identity_router
from wfm.insight.api import router as insight_router
from wfm.intraday.api import router as intraday_router
from wfm.jobs.api import router as jobs_router
from wfm.notifications.api import router as notifications_router
from wfm.overtime.api import router as overtime_router
from wfm.people.api import router as people_router
from wfm.quality.api import router as quality_router
from wfm.reports.api import router as reports_router
from wfm.scheduling.activity_api import router as activity_router
from wfm.scheduling.api import router as scheduling_router
from wfm.scheduling.autoschedule_api import router as autoschedule_router
from wfm.scheduling.compliance_api import router as compliance_router
from wfm.scheduling.recommendation_api import router as recommendation_router
from wfm.servicedesk.api import router as servicedesk_router
from wfm.skills.api import router as skills_router
from wfm.skills.api import wellbeing_router
from wfm.telephony.api import router as telephony_router
from wfm.utilisation.api import router as utilisation_router
from wfm.utilisation.kpi_api import router as service_kpi_router

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
api.add_router("/users", users_router)
api.add_router("/audit", audit_router)
api.add_router("/auth", identity_router)
api.add_router("/system", system_router)
api.add_router("/telephony", telephony_router)
api.add_router("/forecasting", forecasting_router)
api.add_router("/scheduling/compliance-rules", compliance_router)
api.add_router("/scheduling/roster/activities", activity_router)
api.add_router("/scheduling/roster/auto-schedule", autoschedule_router)
api.add_router("/scheduling/recommendations", recommendation_router)
api.add_router("/scheduling", scheduling_router)
api.add_router("/capacity", capacity_router)
api.add_router("/contracts", contracts_router)
api.add_router("/people", people_router)
api.add_router("/jobs", jobs_router)
api.add_router("/insight", insight_router)
api.add_router("/intraday", intraday_router)
api.add_router("/attendance", attendance_router)
api.add_router("/skills", skills_router)
api.add_router("/quality", quality_router)
api.add_router("/service-kpis", service_kpi_router)
api.add_router("/wellbeing", wellbeing_router)
api.add_router("/continuity", continuity_router)
api.add_router("/reports", reports_router)
api.add_router("/notifications", notifications_router)
api.add_router("/overtime", overtime_router)
api.add_router("/service-desk", servicedesk_router)
api.add_router("/utilisation", utilisation_router)
