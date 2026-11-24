from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie

from apps.accounts.models import User
from apps.audit.services import log as audit_log

from . import clock
from .errors import ApiError
from .http import api, get_bool, get_int
from .models import SystemState


@ensure_csrf_cookie
def spa_index(request):
    index_file = settings.FRONTEND_DIST_DIR / "index.html"
    if index_file.exists():
        html = index_file.read_text(encoding="utf-8")
        resp = HttpResponse(html, content_type="text/html; charset=utf-8")
        resp["Cache-Control"] = "no-store"
        return resp
    return JsonResponse(
        {
            "service": "University of Vavuniya LMS API",
            "status": "running",
            "hint": "Run 'npm run dev' in frontend/ and open http://localhost:5173 (or 'npm run build' to serve directly here).",
        }
    )


def healthz(request):
    return JsonResponse({"status": "ok"})


def readyz(request):
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready"})


@api(methods=("GET", "POST", "PUT", "PATCH", "DELETE"), auth=False)
def api_not_found(request):
    raise ApiError("NOT_FOUND", "Unknown API endpoint.", 404)


def _demo_enabled():
    if not settings.DEMO_CLOCK_ENABLED:
        raise ApiError("NOT_FOUND", "Demo tools are disabled.", 404)


def _clock_state():
    state = SystemState.get()
    return {
        "enabled": settings.DEMO_CLOCK_ENABLED,
        "offset_minutes": state.clock_offset_minutes,
        "now": clock.now(),
        "real_now": clock.real_now(),
        "smtp_down": state.smtp_down,
        "scheduler_heartbeat": state.scheduler_heartbeat,
    }


@api(methods=("GET", "POST"), roles=(User.Role.ADMIN,))
def demo_clock(request):
    _demo_enabled()
    if request.method == "POST":
        from apps.notifications.services import process_jobs, scheduler_tick

        state = SystemState.get()
        if get_bool(request.data, "reset"):
            state.clock_offset_minutes = 0
        else:
            days = get_int(request.data, "days", default=0, min_value=-365, max_value=365)
            hours = get_int(
                request.data, "hours", default=0, min_value=-8760, max_value=8760
            )
            state.clock_offset_minutes += days * 24 * 60 + hours * 60
        state.save(update_fields=["clock_offset_minutes"])
        audit_log(
            request.user,
            "demo.clock",
            "system",
            1,
            metadata={"offset_minutes": state.clock_offset_minutes},
        )
        # Trigger a scheduler scan & job run immediately so reminders appear right away in demos
        queued, _ = scheduler_tick()
        processed = process_jobs()
        return {**_clock_state(), "queued_reminders": queued, "processed_jobs": processed}
    return _clock_state()


@api(methods=("POST",), roles=(User.Role.ADMIN,))
def demo_smtp(request):
    """Simulate an SMTP outage so failed/retried jobs can be demonstrated without a mail server."""
    _demo_enabled()
    state = SystemState.get()
    state.smtp_down = get_bool(request.data, "down")
    state.save(update_fields=["smtp_down"])
    audit_log(
        request.user,
        "demo.smtp",
        "system",
        1,
        metadata={"smtp_down": state.smtp_down},
    )
    return _clock_state()
