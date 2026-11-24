from django.conf import settings
from django.db import models


class SystemState(models.Model):
    """One-row table: demo clock offset, simulated SMTP outage and the scheduler heartbeat."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    clock_offset_minutes = models.IntegerField(default=0)
    smtp_down = models.BooleanField(default=False)
    scheduler_heartbeat = models.DateTimeField(null=True, blank=True)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class IdempotencyKey(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    endpoint = models.CharField(max_length=200)
    request_hash = models.CharField(max_length=64)
    response_body = models.JSONField()
    response_status = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
