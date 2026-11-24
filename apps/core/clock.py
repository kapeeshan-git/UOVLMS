"""The only source of "current time" (guide 9.1). Never call timezone.now() elsewhere."""
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

COLOMBO = ZoneInfo("Asia/Colombo")


def real_now():
    """Wall-clock time, ignoring the demo offset (heartbeats, created_at)."""
    return timezone.now()


def now():
    if not settings.DEMO_CLOCK_ENABLED:
        return timezone.now()
    from .models import SystemState

    offset = SystemState.objects.filter(pk=1).values_list("clock_offset_minutes", flat=True).first() or 0
    return timezone.now() + timedelta(minutes=offset)


def local(dt):
    return dt.astimezone(COLOMBO)


def today():
    return local(now()).date()
