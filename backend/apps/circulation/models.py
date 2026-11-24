from django.conf import settings
from django.db import models
from django.db.models import Case, F, Q, Value, When
from django.db.models.functions import Coalesce


class CirculationRule(models.Model):
    patron_category = models.CharField(max_length=30)
    academic_year = models.PositiveSmallIntegerField(null=True, blank=True)
    section = models.ForeignKey(
        "catalog.SectionPolicy",
        on_delete=models.PROTECT,
        db_column="section_code",
        related_name="rules",
    )
    is_allowed = models.BooleanField(default=True)
    loan_period_days = models.PositiveSmallIntegerField(default=7)
    max_loans = models.PositiveSmallIntegerField(default=2)
    max_renewals = models.PositiveSmallIntegerField(default=0)
    reminder_hours_before = models.PositiveSmallIntegerField(default=24)
    final_reminder_hours_before = models.PositiveSmallIntegerField(default=3)
    # MySQL unique indexes allow many NULLs, so uniqueness uses COALESCE(year, 0) (guide 6.6).
    academic_year_key = models.GeneratedField(
        expression=Coalesce(F("academic_year"), Value(0)),
        output_field=models.PositiveSmallIntegerField(),
        db_persist=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patron_category", "academic_year_key", "section"],
                name="uniq_circulation_rule",
            ),
        ]
        ordering = ["patron_category", "academic_year", "section_id"]


class ClosedDay(models.Model):
    day = models.DateField(primary_key=True)
    reason = models.CharField(max_length=200)

    class Meta:
        ordering = ["day"]


class Loan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE"
        RETURNED = "RETURNED"
        LOST = "LOST"

    patron = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="loans",
    )
    copy = models.ForeignKey(
        "catalog.BookCopy", on_delete=models.PROTECT, related_name="loans"
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    issued_at = models.DateTimeField()
    due_at = models.DateTimeField()
    returned_at = models.DateTimeField(null=True, blank=True)
    renewal_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    title_snapshot = models.CharField(max_length=500)
    accession_snapshot = models.CharField(max_length=50)
    section_snapshot = models.CharField(max_length=20)
    reminder_hours = models.PositiveSmallIntegerField(default=24)
    final_reminder_hours = models.PositiveSmallIntegerField(default=3)
    # copy_id while ACTIVE, NULL otherwise. Its unique index = "one active loan per copy".
    active_copy_id = models.GeneratedField(
        expression=Case(
            When(status="ACTIVE", then=F("copy")),
            default=Value(None),
            output_field=models.BigIntegerField(null=True),
        ),
        output_field=models.BigIntegerField(null=True),
        db_persist=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["active_copy_id"], name="uniq_active_loan_per_copy"
            ),
            models.CheckConstraint(
                condition=Q(renewal_count__gte=0),
                name="loan_renewals_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["patron", "status"]),
            models.Index(fields=["status", "due_at"]),
        ]
        ordering = ["-issued_at", "-id"]


class Fine(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN"
        SETTLED = "SETTLED"

    loan = models.OneToOneField(
        Loan, on_delete=models.PROTECT, related_name="fine"
    )
    patron = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="fines",
    )
    days_late = models.PositiveIntegerField()
    rate_applied = models.DecimalField(max_digits=10, decimal_places=2)
    calculated_amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.OPEN
    )
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(balance__gte=0), name="fine_balance_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(calculated_amount__gte=0),
                name="fine_amount_non_negative",
            ),
        ]
        indexes = [models.Index(fields=["patron", "status"])]
        ordering = ["-id"]


class FineTransaction(models.Model):
    class Type(models.TextChoices):
        PAYMENT = "PAYMENT"
        WAIVER = "WAIVER"
        ADJUSTMENT = "ADJUSTMENT"

    fine = models.ForeignKey(
        Fine, on_delete=models.PROTECT, related_name="transactions"
    )
    type = models.CharField(max_length=12, choices=Type.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    reason = models.CharField(max_length=500, blank=True)
    receipt_ref = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(amount=0), name="fine_tx_non_zero"
            )
        ]
        ordering = ["id"]
