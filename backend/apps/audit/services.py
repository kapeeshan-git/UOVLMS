from apps.core import clock
from apps.core.middleware import current_request_id

from .models import AuditEvent

_SENSITIVE = ("password", "token", "secret")


def _redact(metadata):
    return {
        k: ("[redacted]" if any(s in k.lower() for s in _SENSITIVE) else v)
        for k, v in (metadata or {}).items()
    }


def log(actor, action, resource_type, resource_id=None, reason="", metadata=None):
    """Write an audit row. Call inside the same transaction as the change it records."""
    return AuditEvent.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        timestamp=clock.now(),
        request_id=current_request_id(),
        reason=(reason or "")[:500],
        metadata_redacted=_redact(metadata),
    )
