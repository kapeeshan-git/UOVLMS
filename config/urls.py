from django.conf import settings
from django.urls import include, path, re_path
from django.views.static import serve

from apps.core import views as core_views

urlpatterns = [
    path("api/v1/", include("config.api_urls")),
    path("healthz", core_views.healthz),
    path("readyz", core_views.readyz),
    # The SPA's JS/CSS are served straight from frontend/ (no collectstatic, no build step).
    re_path(r"^static/(?P<path>.+)$", serve, {"document_root": settings.FRONTEND_DIR}),
    path("", core_views.spa_index),
]
