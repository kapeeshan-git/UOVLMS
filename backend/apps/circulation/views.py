from django.conf import settings
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import ADMIN, STAFF, User
from apps.audit.services import log as audit_log
from apps.catalog.models import SectionPolicy
from apps.core import clock
from apps.core.errors import ApiError
from apps.core.http import (
    api,
    get_bool,
    get_choice,
    get_date,
    get_int,
    get_str,
    paginate,
)

from .models import CirculationRule, ClosedDay, Fine, Loan
from .services import fines as fine_svc
from .services import loans as loan_svc


def _patron_brief(u):
    return {
        "id": u.id,
        "username": u.username,
        "full_name": u.full_name,
        "reg_number": u.reg_number,
    }


def loan_dict(loan, now=None):
    now = now or clock.now()
    fine = getattr(loan, "fine", None)
    return {
        "id": loan.id,
        "patron": _patron_brief(loan.patron),
        "copy": {"id": loan.copy_id, "accession_number": loan.accession_snapshot},
        "title": loan.title_snapshot,
        "section": loan.section_snapshot,
        "issued_at": loan.issued_at,
        "due_at": loan.due_at,
        "returned_at": loan.returned_at,
        "renewal_count": loan.renewal_count,
        "status": loan.status,
        "overdue": loan.status == Loan.Status.ACTIVE and loan.due_at < now,
        "fine": (
            {"id": fine.id, "balance": fine.balance, "status": fine.status}
            if fine
            else None
        ),
    }


def fine_dict(f, with_transactions=False):
    data = {
        "id": f.id,
        "loan_id": f.loan_id,
        "patron": _patron_brief(f.patron),
        "title": f.loan.title_snapshot,
        "accession_number": f.loan.accession_snapshot,
        "days_late": f.days_late,
        "rate_applied": f.rate_applied,
        "calculated_amount": f.calculated_amount,
        "balance": f.balance,
        "status": f.status,
        "created_at": f.created_at,
    }
    if with_transactions:
        data["transactions"] = [
            {
                "id": t.id,
                "type": t.type,
                "amount": t.amount,
                "actor": t.actor.username,
                "reason": t.reason,
                "receipt_ref": t.receipt_ref,
                "created_at": t.created_at,
            }
            for t in f.transactions.select_related("actor")
        ]
    return data


def _loans_qs():
    return Loan.objects.select_related("patron", "fine")


def _fines_qs():
    return Fine.objects.select_related("patron", "loan")


# --- desk ---


@api(roles=STAFF)
def patron_lookup(request):
    from apps.accounts.views import patron_detail_dict

    code = request.GET.get("code", "").strip()[:150]
    if not code:
        raise ApiError(
            "VALIDATION_ERROR",
            "code: Scan a card or type a registration number.",
            400,
        )
    patron = (
        User.objects.select_related("department")
        .filter(reg_number__iexact=code)
        .first()
        or User.objects.select_related("department")
        .filter(username__iexact=code)
        .first()
    )
    if patron is None:
        raise ApiError("PATRON_NOT_FOUND", f"No patron matches '{code}'.", 404)
    now = clock.now()
    active = (
        _loans_qs()
        .filter(patron=patron, status=Loan.Status.ACTIVE)
        .order_by("due_at")
    )
    return {
        "patron": patron_detail_dict(patron),
        "loans": [loan_dict(l, now) for l in active],
    }


@api(roles=STAFF)
def patron_loans(request, pk):
    qs = _loans_qs().filter(patron_id=pk)
    now = clock.now()
    return paginate(request, qs, lambda l: loan_dict(l, now))


@api(roles=STAFF)
def patron_clearance(request, pk):
    return fine_svc.check_clearance(User.objects.get(pk=pk))


@api(methods=("GET", "POST"), roles=STAFF, idempotent=True)
def loans(request):
    if request.method == "POST":
        loan = loan_svc.issue_copy(
            librarian=request.user,
            patron_id=get_int(request.data, "patron_id", required=True),
            accession_number=get_str(
                request.data, "accession_number", required=True, max_len=50
            ),
        )
        return (
            {
                **loan_dict(_loans_qs().get(pk=loan.pk)),
                "request_id": request.request_id,
            },
            201,
        )
    qs = _loans_qs()
    now = clock.now()
    status = request.GET.get("status")
    if status in Loan.Status.values:
        qs = qs.filter(status=status)
    if request.GET.get("patron"):
        qs = qs.filter(patron_id=get_int(request.GET, "patron"))
    if request.GET.get("accession"):
        qs = qs.filter(accession_snapshot=request.GET["accession"].strip()[:50])
    if request.GET.get("overdue") in ("1", "true"):
        qs = qs.filter(status=Loan.Status.ACTIVE, due_at__lt=now)
    return paginate(request, qs, lambda l: loan_dict(l, now))


@api(methods=("POST",), roles=STAFF, idempotent=True)
def loan_return(request):
    loan, fine = loan_svc.return_copy(
        librarian=request.user,
        accession_number=get_str(
            request.data, "accession_number", required=True, max_len=50
        ),
    )
    loan = _loans_qs().get(pk=loan.pk)
    return {
        "loan": loan_dict(loan),
        "fine": fine_dict(_fines_qs().get(pk=fine.pk)) if fine else None,
        "copy_status": "AVAILABLE",
    }


@api()
def loans_mine(request):
    qs = _loans_qs().filter(patron=request.user)
    if request.GET.get("status") in Loan.Status.values:
        qs = qs.filter(status=request.GET["status"])
    now = clock.now()
    return paginate(request, qs, lambda l: loan_dict(l, now))


@api(roles=STAFF)
def loan_detail(request, pk):
    return loan_dict(_loans_qs().get(pk=pk))


@api(methods=("POST",), idempotent=True)
def loan_renew(request, pk):
    loan = loan_svc.renew_loan(
        actor=request.user,
        loan_id=pk,
        reason=get_str(request.data, "reason", max_len=500),
    )
    return loan_dict(_loans_qs().get(pk=loan.pk))


@api(methods=("POST",), roles=STAFF)
def loan_lost(request, pk):
    loan = loan_svc.declare_lost(
        actor=request.user,
        loan_id=pk,
        reason=get_str(request.data, "reason", max_len=500),
    )
    return loan_dict(_loans_qs().get(pk=loan.pk))


# --- fines ---


@api(roles=STAFF)
def fines(request):
    qs = _fines_qs()
    if request.GET.get("status") in Fine.Status.values:
        qs = qs.filter(status=request.GET["status"])
    if request.GET.get("patron"):
        qs = qs.filter(patron_id=get_int(request.GET, "patron"))
    q = request.GET.get("q", "").strip()[:100]
    if q:
        qs = qs.filter(
            Q(patron__full_name__icontains=q)
            | Q(patron__reg_number__icontains=q)
            | Q(patron__username__icontains=q)
        )
    return paginate(request, qs, fine_dict)


@api()
def fines_mine(request):
    qs = _fines_qs().filter(patron=request.user)
    return {
        **paginate(request, qs, lambda f: fine_dict(f, True)),
        "balance": fine_svc.open_balance(request.user.id),
    }


@api(methods=("GET", "POST"), roles=STAFF, idempotent=True)
def fine_transactions(request, pk):
    if request.method == "POST":
        fine_svc.record_fine_transaction(request.user, pk, request.data)
        return fine_dict(_fines_qs().get(pk=pk), True), 201
    return fine_dict(_fines_qs().get(pk=pk), True)


# --- admin: rules and calendar ---


def rule_dict(r):
    return {
        "id": r.id,
        "patron_category": r.patron_category,
        "academic_year": r.academic_year,
        "section_code": r.section_id,
        "is_allowed": r.is_allowed,
        "loan_period_days": r.loan_period_days,
        "max_loans": r.max_loans,
        "max_renewals": r.max_renewals,
        "reminder_hours_before": r.reminder_hours_before,
        "final_reminder_hours_before": r.final_reminder_hours_before,
    }


@api(methods=("GET", "PUT"), roles={"GET": STAFF, "PUT": ADMIN})
def admin_rules(request):
    """PUT replaces the whole rule set (rows missing from the list are deleted)."""
    if request.method == "PUT":
        items = request.data.get("rules")
        if not isinstance(items, list) or len(items) > 200:
            raise ApiError(
                "VALIDATION_ERROR",
                "rules: Must be a list.",
                400,
                {"rules": "Must be a list."},
            )
        sections = set(SectionPolicy.objects.values_list("code", flat=True))
        seen, keep = set(), []
        with transaction.atomic():
            for item in items:
                if not isinstance(item, dict):
                    raise ApiError(
                        "VALIDATION_ERROR",
                        "rules: Each rule must be an object.",
                        400,
                    )
                fields = {
                    "patron_category": get_choice(
                        item, "patron_category", User.Category.values, required=True
                    ),
                    "academic_year": get_int(
                        item, "academic_year", min_value=1, max_value=10
                    ),
                    "section_id": get_str(
                        item, "section_code", required=True, max_len=20
                    ),
                    "is_allowed": get_bool(item, "is_allowed", True),
                    "loan_period_days": get_int(
                        item,
                        "loan_period_days",
                        required=True,
                        min_value=0,
                        max_value=365,
                    ),
                    "max_loans": get_int(
                        item, "max_loans", required=True, min_value=0, max_value=100
                    ),
                    "max_renewals": get_int(
                        item, "max_renewals", default=0, min_value=0, max_value=20
                    ),
                    "reminder_hours_before": get_int(
                        item,
                        "reminder_hours_before",
                        default=24,
                        min_value=0,
                        max_value=720,
                    ),
                    "final_reminder_hours_before": get_int(
                        item,
                        "final_reminder_hours_before",
                        default=3,
                        min_value=0,
                        max_value=720,
                    ),
                }
                if fields["section_id"] not in sections:
                    raise ApiError(
                        "VALIDATION_ERROR",
                        f"section_code: Unknown section {fields['section_id']}.",
                        400,
                    )
                key = (
                    fields["patron_category"],
                    fields["academic_year"],
                    fields["section_id"],
                )
                if key in seen:
                    raise ApiError(
                        "VALIDATION_ERROR", f"Duplicate rule for {key}.", 400
                    )
                seen.add(key)
                rule = CirculationRule.objects.filter(
                    patron_category=key[0],
                    academic_year=key[1],
                    section_id=key[2],
                ).first()
                if rule:
                    CirculationRule.objects.filter(pk=rule.pk).update(**fields)
                    keep.append(rule.pk)
                else:
                    keep.append(CirculationRule.objects.create(**fields).pk)
            CirculationRule.objects.exclude(pk__in=keep).delete()
            audit_log(
                request.user,
                "rules.update",
                "circulation_rule",
                None,
                metadata={"count": len(keep)},
            )
    return {"results": [rule_dict(r) for r in CirculationRule.objects.all()]}


@api(methods=("GET", "POST"), roles={"GET": STAFF, "POST": ADMIN})
def admin_closed_days(request):
    if request.method == "POST":
        day = get_date(request.data, "day", required=True)
        reason = get_str(request.data, "reason", required=True, max_len=200)
        ClosedDay.objects.update_or_create(day=day, defaults={"reason": reason})
        audit_log(
            request.user,
            "calendar.add",
            "closed_day",
            None,
            reason=reason,
            metadata={"day": day.isoformat()},
        )
    return {
        "results": [
            {"day": d.day, "reason": d.reason} for d in ClosedDay.objects.all()
        ],
        "weekly_closed": sorted(settings.LIBRARY_CLOSED_WEEKDAYS),
    }


@api(methods=("DELETE",), roles=ADMIN)
def admin_closed_day_delete(request, day):
    deleted, _ = ClosedDay.objects.filter(
        day=get_date({"day": day}, "day", required=True)
    ).delete()
    if not deleted:
        raise ApiError("NOT_FOUND", "No closed day on that date.", 404)
    audit_log(
        request.user,
        "calendar.remove",
        "closed_day",
        None,
        metadata={"day": day},
    )
    return None
