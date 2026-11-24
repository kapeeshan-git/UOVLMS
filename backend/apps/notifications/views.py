from apps.accounts.models import ADMIN
from apps.audit.services import log as audit_log
from apps.core.errors import ApiError
from apps.core.http import api, paginate
from apps.core.models import SystemState

from .models import Job, Notification
from .services import REDACTED_TEMPLATES, process_jobs, retry_job, scheduler_tick


def job_dict(j):
    return {
        "id": j.id,
        "type": j.type,
        "payload": j.payload,
        "run_at": j.run_at,
        "status": j.status,
        "attempts": j.attempts,
        "error_category": j.error_category,
        "last_error": j.last_error,
        "created_at": j.created_at,
    }


def notification_dict(n):
    redacted = n.template_id in REDACTED_TEMPLATES
    return {
        "id": n.id,
        "to": n.user.email,
        "user": n.user.username,
        "template_id": n.template_id,
        "status": n.status,
        "attempts": n.attempts,
        "subject": n.subject,
        "body": (
            "[hidden: contains a password reset link]" if redacted else n.body
        ),
        "created_at": n.created_at,
        "sent_at": n.sent_at,
        "error_category": n.error_category,
    }


@api(roles=ADMIN)
def jobs(request):
    qs = Job.objects.all()
    if request.GET.get("status") in Job.Status.values:
        qs = qs.filter(status=request.GET["status"])
    state = SystemState.get()
    counts = {s: Job.objects.filter(status=s).count() for s in Job.Status.values}
    return {
        **paginate(request, qs, job_dict),
        "counts": counts,
        "scheduler_heartbeat": state.scheduler_heartbeat,
        "smtp_down": state.smtp_down,
    }


@api(methods=("POST",), roles=ADMIN)
def jobs_run_now(request):
    queued, reaped = scheduler_tick()
    processed = process_jobs(limit=50)
    return {"queued": queued, "reaped": reaped, "processed": processed}


@api(methods=("POST",), roles=ADMIN)
def job_retry(request, pk):
    job, ok = retry_job(pk)
    if not ok:
        raise ApiError("JOB_NOT_RETRYABLE", f"Job is {job.status}.", 409)
    audit_log(request.user, "job.retry", "job", job.id)
    process_jobs(limit=5)
    job.refresh_from_db()
    return job_dict(job)


@api(roles=ADMIN)
def notifications(request):
    qs = Notification.objects.select_related("user")
    if request.GET.get("status") in Notification.Status.values:
        qs = qs.filter(status=request.GET["status"])
    return paginate(request, qs, notification_dict)
