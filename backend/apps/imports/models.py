from django.conf import settings
from django.db import models


class ImportRun(models.Model):
    class Kind(models.TextChoices):
        BOOKS_COPIES = "BOOKS_COPIES"
        PATRONS = "PATRONS"

    class Status(models.TextChoices):
        VALIDATED = "VALIDATED"
        APPLIED = "APPLIED"
        FAILED = "FAILED"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    file_name = models.CharField(max_length=200)
    dry_run = models.BooleanField(default=True)
    status = models.CharField(max_length=12, choices=Status.choices)
    summary = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["-id"]
