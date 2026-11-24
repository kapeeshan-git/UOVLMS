from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Append-only. There are no update/delete code paths; production grants INSERT/SELECT only."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=60)
    resource_type = models.CharField(max_length=40)
    resource_id = models.BigIntegerField(null=True, blank=True)
    timestamp = models.DateTimeField()
    request_id = models.CharField(max_length=64, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    metadata_redacted = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["resource_type", "resource_id"]), models.Index(fields=["timestamp"])]
        ordering = ["-id"]
