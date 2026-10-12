from django.urls import path

from wfm.api import api
from wfm.core import health

urlpatterns = [
    path("healthz", health.healthz),
    path("readyz", health.readyz),
    path("api/v1/", api.urls),
]
