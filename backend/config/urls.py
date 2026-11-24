from django.conf import settings
from django.urls import include, path, re_path
from django.views.static import serve

from apps.core import views as core_views

urlpatterns = [
    path("api/v1/", include("config.api_urls")),
    path("healthz", core_views.healthz),
    path("readyz", core_views.readyz),
    re_path(
        r"^assets/(?P<path>.+)$",
        serve,
        {"document_root": settings.FRONTEND_DIST_DIR / "assets"},
    ),
    re_path(r"^(?!api/|healthz|readyz).*$", core_views.spa_index),
]
