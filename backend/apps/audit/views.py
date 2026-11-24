from apps.accounts.models import ADMIN
from apps.core.http import api, paginate

from .models import AuditEvent


def event_dict(e):
    return {
        "id": e.id,
        "actor": e.actor.username if e.actor_id else None,
        "action": e.action,
        "resource_type": e.resource_type,
        "resource_id": e.resource_id,
        "timestamp": e.timestamp,
        "request_id": e.request_id,
        "reason": e.reason,
        "metadata": e.metadata_redacted,
    }


@api(roles=ADMIN)
def audit_list(request):
    qs = AuditEvent.objects.select_related("actor")
    for param, field in (
        ("action", "action__startswith"),
        ("resource_type", "resource_type"),
        ("resource_id", "resource_id"),
        ("actor", "actor__username"),
    ):
        value = request.GET.get(param, "").strip()[:60]
        if value:
            qs = qs.filter(**{field: value})
    return paginate(request, qs, event_dict, default_size=50)
