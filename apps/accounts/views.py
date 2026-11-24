from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models import Q
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import ensure_csrf_cookie

from apps.audit.services import log as audit_log
from apps.core import clock
from apps.core.errors import ApiError
from apps.core.http import api, get_choice, get_str, hit, paginate, rate_limited, too_many

from . import services
from .models import ADMIN, STAFF, Department, User


def user_me(u):
    return {
        "id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email, "role": u.role,
        "reg_number": u.reg_number, "patron_category": u.patron_category, "status": u.status,
    }


def patron_summary(u):
    return {
        **user_me(u),
        "department": u.department.name if u.department_id else None,
        "academic_year": services.academic_year_of(u, clock.today()),
    }


def patron_detail_dict(u):
    from apps.circulation.services.fines import open_balance
    from apps.circulation.models import Loan

    return {
        **patron_summary(u),
        "intake_year": u.intake_year,
        "department_id": u.department_id,
        "preferred_language": u.preferred_language,
        "is_active": u.is_active,
        "created_at": u.created_at,
        "active_loans": Loan.objects.filter(patron=u, status=Loan.Status.ACTIVE).count(),
        "fine_balance": open_balance(u.id),
    }


# --- auth ------------------------------------------------------------------------------------

@ensure_csrf_cookie
@api(auth=False)
def csrf(request):
    return {"ok": True}


@api(methods=("POST",), auth=False)
def login_view(request):
    username = get_str(request.data, "username", required=True, max_len=150)
    password = get_str(request.data, "password", required=True, max_len=256, strip=False)
    ip = request.META.get("REMOTE_ADDR", "")
    if too_many(f"login-ip:{ip}", 30) or too_many(f"login-user:{username.lower()}", 10):
        raise rate_limited()
    user = authenticate(request, username=username, password=password)
    if user is None or user.status == User.Status.INACTIVE:
        hit(f"login-ip:{ip}", 900)
        hit(f"login-user:{username.lower()}", 900)
        raise ApiError("INVALID_CREDENTIALS", "Invalid username or password.", 400)  # no account hints
    login(request, user)
    return {"user": user_me(user)}


@api(methods=("POST",))
def logout_view(request):
    logout(request)
    return None


@api()
def me(request):
    return {"user": user_me(request.user), "demo_clock": settings.DEMO_CLOCK_ENABLED, "now": clock.now()}


@api(methods=("POST",), auth=False)
def password_reset(request):
    from apps.notifications.services import queue_email

    email = get_str(request.data, "email", required=True, max_len=254)
    ip = request.META.get("REMOTE_ADDR", "")
    if too_many(f"reset:{ip}", 5):
        raise rate_limited()
    hit(f"reset:{ip}", 900)
    for user in User.objects.filter(email__iexact=email, is_active=True).exclude(status=User.Status.INACTIVE)[:3]:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        link = f"{settings.SITE_URL}/#/reset?uid={uid}&token={token}"
        queue_email(user, "password_reset", {"name": user.full_name, "link": link},
                    dedupe_key=f"password_reset:{user.id}:{token}", related=("user", user.id))
    # Same answer whether or not the email exists.
    return {"ok": True, "message": "If that email belongs to an account, a reset link has been sent."}


@api(methods=("POST",), auth=False)
def password_reset_confirm(request):
    uid = get_str(request.data, "uid", required=True, max_len=64)
    token = get_str(request.data, "token", required=True, max_len=128)
    password = get_str(request.data, "new_password", required=True, max_len=128, strip=False)
    try:
        user = User.objects.get(pk=int(force_str(urlsafe_base64_decode(uid))))
    except (ValueError, TypeError, OverflowError, User.DoesNotExist):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        raise ApiError("INVALID_TOKEN", "This reset link is invalid or has expired.", 400)
    try:
        validate_password(password, user)
    except ValidationError as e:
        raise ApiError("VALIDATION_ERROR", " ".join(e.messages), 400, {"new_password": " ".join(e.messages)})
    user.set_password(password)
    user.save(update_fields=["password"])
    audit_log(user, "auth.password_reset", "user", user.id)
    return {"ok": True}


# --- patrons ---------------------------------------------------------------------------------

@api(roles=STAFF)
def departments(request):
    return {"results": [{"id": d.id, "name": d.name, "faculty": d.faculty} for d in Department.objects.all()]}


@api(methods=("GET", "POST"), roles=STAFF)
def patrons(request):
    if request.method == "POST":
        user = services.create_patron(request.user, request.data)
        return patron_detail_dict(user), 201
    qs = User.objects.select_related("department").order_by("full_name")
    q = request.GET.get("q", "").strip()[:100]
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(full_name__icontains=q) | Q(reg_number__icontains=q))
    if request.GET.get("role") in User.Role.values:
        qs = qs.filter(role=request.GET["role"])
    if request.GET.get("status") in User.Status.values:
        qs = qs.filter(status=request.GET["status"])
    return paginate(request, qs, patron_summary)


@api(methods=("GET", "PATCH"), roles=STAFF)
def patron_detail(request, pk):
    user = User.objects.select_related("department").get(pk=pk)
    if request.method == "PATCH":
        user = services.update_patron(request.user, user, request.data)
    return patron_detail_dict(user)


@api(methods=("POST",), roles=STAFF)
def patron_status(request, pk):
    from apps.circulation.services.fines import check_clearance

    user = User.objects.get(pk=pk)
    status = get_choice(request.data, "status", User.Status.values, required=True)
    reason = get_str(request.data, "reason", max_len=500)
    if status == User.Status.GRADUATED:
        clearance = check_clearance(user)
        if not clearance["cleared"]:
            raise ApiError("CLEARANCE_FAILED", "Patron has active loans or unpaid fines.", 422)
    services.set_patron_status(request.user, user, status, reason)
    return patron_detail_dict(user)
