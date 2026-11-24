import re

from django.conf import settings
from django.db import transaction

from apps.audit.services import log as audit_log
from apps.core.errors import ApiError, forbidden
from apps.core.http import get_choice, get_int, get_str

from .models import Department, User

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def academic_year_of(user, today):
    """Student year computed from intake year (guide 9.2); never stored."""
    if user.patron_category != User.Category.STUDENT or not user.intake_year:
        return None
    start_year = today.year if (today.month, today.day) >= tuple(settings.ACADEMIC_YEAR_START) else today.year - 1
    return max(1, min(settings.MAX_STUDENT_YEAR, start_year - user.intake_year + 1))


def _apply_fields(actor, user, data, creating):
    changed = {}

    def put(field, value):
        if getattr(user, field) != value:
            changed[field] = value
            setattr(user, field, value)

    if creating or "full_name" in data:
        put("full_name", get_str(data, "full_name", required=True, max_len=200))
    if creating or "email" in data:
        email = get_str(data, "email", max_len=254)
        if email and not EMAIL_RE.match(email):
            raise ApiError("VALIDATION_ERROR", "email: Enter a valid email address.", 400, {"email": "Enter a valid email address."})
        put("email", email)
    if creating or "reg_number" in data:
        reg = get_str(data, "reg_number", max_len=50) or None
        if reg and User.objects.filter(reg_number=reg).exclude(pk=user.pk).exists():
            raise ApiError("VALIDATION_ERROR", "reg_number: Already used.", 400, {"reg_number": "Already used."})
        put("reg_number", reg)
    if creating or "patron_category" in data:
        put("patron_category", get_choice(data, "patron_category", User.Category.values, default=""))
    if creating or "intake_year" in data:
        put("intake_year", get_int(data, "intake_year", min_value=1990, max_value=2100))
    if creating or "department_id" in data:
        dep_id = get_int(data, "department_id")
        if dep_id and not Department.objects.filter(pk=dep_id).exists():
            raise ApiError("VALIDATION_ERROR", "department_id: Unknown department.", 400, {"department_id": "Unknown department."})
        put("department_id", dep_id)
    if "role" in data:
        role = get_choice(data, "role", User.Role.values, required=True)
        if role != user.role and actor.role != User.Role.ADMIN:
            raise forbidden("Only an admin can change roles.")
        put("role", role)
    if user.patron_category == User.Category.STUDENT and not user.intake_year:
        raise ApiError("VALIDATION_ERROR", "intake_year: Required for students.", 400, {"intake_year": "Required for students."})
    return changed


@transaction.atomic
def create_patron(actor, data):
    username = get_str(data, "username", required=True, max_len=150)
    if not re.match(r"^[\w.@+-]+$", username):
        raise ApiError("VALIDATION_ERROR", "username: Letters, digits and @/./+/-/_ only.", 400, {"username": "Invalid characters."})
    if User.objects.filter(username__iexact=username).exists():
        raise ApiError("VALIDATION_ERROR", "username: Already taken.", 400, {"username": "Already taken."})
    user = User(username=username, role=User.Role.MEMBER)
    changed = _apply_fields(actor, user, data, creating=True)
    password = get_str(data, "password", max_len=128, strip=False)
    if password:
        if len(password) < 8:
            raise ApiError("VALIDATION_ERROR", "password: At least 8 characters.", 400, {"password": "At least 8 characters."})
        user.set_password(password)
    else:
        user.set_unusable_password()  # the patron sets one via "forgot password"
    user.save()
    audit_log(actor, "patron.create", "user", user.id, metadata={k: str(v) for k, v in changed.items()})
    return user


@transaction.atomic
def update_patron(actor, user, data):
    if user.role != User.Role.MEMBER and actor.role != User.Role.ADMIN:
        raise forbidden("Only an admin can edit staff accounts.")
    changed = _apply_fields(actor, user, data, creating=False)
    if changed:
        user.save()
        audit_log(actor, "patron.update", "user", user.id, metadata={k: str(v) for k, v in changed.items()})
    return user


@transaction.atomic
def set_patron_status(actor, user, status, reason=""):
    if status in (User.Status.SUSPENDED, User.Status.INACTIVE) and not reason:
        raise ApiError("VALIDATION_ERROR", "reason: Required for this status.", 400, {"reason": "Required."})
    if user.role != User.Role.MEMBER and actor.role != User.Role.ADMIN:
        raise forbidden("Only an admin can change staff accounts.")
    old = user.status
    user.status = status
    user.save(update_fields=["status"])
    audit_log(actor, "patron.status", "user", user.id, reason=reason, metadata={"from": old, "to": status})
    return user
