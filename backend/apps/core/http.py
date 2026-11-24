"""JSON API helpers, auth/role checks, idempotency, pagination, rate limiting, and validation."""
import hashlib
import json
import logging
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from .errors import ApiError

log = logging.getLogger("lms.api")


class Encoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return (
                timezone.localtime(o).isoformat(timespec="seconds")
                if timezone.is_aware(o)
                else o.isoformat()
            )
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, time):
            return o.strftime("%H:%M")
        if isinstance(o, Decimal):
            return f"{o:.2f}"
        return super().default(o)


def to_jsonable(data):
    return json.loads(json.dumps(data, cls=Encoder))


def json_response(data, status=200):
    return JsonResponse(
        data,
        status=status,
        safe=False,
        encoder=Encoder,
        json_dumps_params={"ensure_ascii": False},
    )


def _error_response(request, err):
    return json_response(err.payload(getattr(request, "request_id", "")), err.status)


def _parse_body(request):
    if request.method in ("GET", "HEAD", "DELETE"):
        return {}
    ctype = request.content_type or ""
    if ctype.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        return request.POST.dict()
    if not request.body:
        return {}
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        raise ApiError("VALIDATION_ERROR", "Request body must be valid JSON.", 400)
    if not isinstance(data, dict):
        raise ApiError("VALIDATION_ERROR", "Request body must be a JSON object.", 400)
    return data


def _split(result):
    if isinstance(result, tuple):
        return result[0], result[1]
    return result, 200


def _to_response(result):
    if isinstance(result, HttpResponse):
        return result
    data, status = _split(result)
    if data is None:
        return HttpResponse(status=204)
    return json_response(data, status)


def _idempotent(request, fn, args, kwargs):
    from .models import IdempotencyKey

    key = (request.headers.get("Idempotency-Key") or "").strip()
    if not key or len(key) > 64:
        raise ApiError(
            "VALIDATION_ERROR",
            "An Idempotency-Key header (max 64 characters) is required.",
            400,
        )
    req_hash = hashlib.sha256(request.body or b"").hexdigest()

    existing = IdempotencyKey.objects.filter(key=key).first()
    if existing:
        if (
            existing.user_id != request.user.id
            or existing.endpoint != request.path
            or existing.request_hash != req_hash
        ):
            raise ApiError(
                "IDEMPOTENCY_CONFLICT",
                "This Idempotency-Key was already used for a different request.",
                409,
            )
        resp = json_response(existing.response_body, existing.response_status)
        resp["Idempotent-Replay"] = "true"
        return resp

    data, status = _split(fn(request, *args, **kwargs))
    body = to_jsonable(data)
    try:
        IdempotencyKey.objects.create(
            key=key,
            user=request.user,
            endpoint=request.path,
            request_hash=req_hash,
            response_body=body,
            response_status=status,
        )
    except IntegrityError:
        pass
    return json_response(body, status)


def api(methods=("GET",), roles=None, auth=True, idempotent=False):
    """Decorator for JSON API views."""

    def deco(fn):
        @wraps(fn)
        def wrapper(request, *args, **kwargs):
            try:
                if request.method not in methods:
                    raise ApiError(
                        "METHOD_NOT_ALLOWED",
                        f"Method {request.method} is not allowed here.",
                        405,
                    )
                if auth and not request.user.is_authenticated:
                    raise ApiError("UNAUTHENTICATED", "Please log in.", 401)
                allowed = (
                    roles.get(request.method) if isinstance(roles, dict) else roles
                )
                if allowed and request.user.role not in allowed:
                    raise ApiError(
                        "FORBIDDEN", "You do not have permission to do this.", 403
                    )
                request.data = _parse_body(request)
                if idempotent and request.method == "POST":
                    return _idempotent(request, fn, args, kwargs)
                return _to_response(fn(request, *args, **kwargs))
            except ApiError as err:
                return _error_response(request, err)
            except ObjectDoesNotExist:
                return _error_response(request, ApiError("NOT_FOUND", "Not found.", 404))
            except Exception:
                log.exception(
                    "Unhandled API error (request_id=%s)",
                    getattr(request, "request_id", ""),
                )
                return _error_response(
                    request,
                    ApiError(
                        "INTERNAL_ERROR",
                        "Something went wrong. Please try again.",
                        500,
                    ),
                )

        return wrapper

    return deco


# --- pagination ---


def paginate(request, queryset, serialize, max_size=100, default_size=25):
    page = _int_or(request.GET.get("page"), 1, minimum=1)
    size = min(max_size, _int_or(request.GET.get("page_size"), default_size, minimum=1))
    total = queryset.count()
    items = queryset[(page - 1) * size : page * size]
    return {
        "results": [serialize(x) for x in items],
        "page": page,
        "page_size": size,
        "total": total,
    }


def _int_or(value, default, minimum=None):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, v) if minimum is not None else v


# --- rate limiting ---


def too_many(key, limit):
    return (cache.get("rl:" + key) or 0) >= limit


def hit(key, window_seconds):
    k = "rl:" + key
    if not cache.add(k, 1, window_seconds):
        try:
            cache.incr(k)
        except ValueError:
            cache.set(k, 1, window_seconds)


def rate_limited():
    return ApiError(
        "RATE_LIMITED",
        "Too many attempts. Please wait a few minutes and try again.",
        429,
    )


# --- validation helpers ---


def _fail(name, msg):
    raise ApiError("VALIDATION_ERROR", f"{name}: {msg}", 400, {name: msg})


def _missing(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def get_str(data, name, *, required=False, max_len=255, default="", strip=True):
    v = data.get(name)
    if _missing(v):
        if required:
            _fail(name, "This field is required.")
        return default
    if isinstance(v, bool) or not isinstance(v, (str, int)):
        _fail(name, "Must be text.")
    v = str(v).strip() if strip else str(v)
    if len(v) > max_len:
        _fail(name, f"Must be at most {max_len} characters.")
    return v


def get_int(
    data, name, *, required=False, min_value=None, max_value=None, default=None
):
    v = data.get(name)
    if _missing(v):
        if required:
            _fail(name, "This field is required.")
        return default
    if isinstance(v, bool):
        _fail(name, "Must be a whole number.")
    try:
        v = int(str(v).strip())
    except ValueError:
        _fail(name, "Must be a whole number.")
    if min_value is not None and v < min_value:
        _fail(name, f"Must be at least {min_value}.")
    if max_value is not None and v > max_value:
        _fail(name, f"Must be at most {max_value}.")
    return v


def get_decimal(data, name, *, required=False, default=None):
    v = data.get(name)
    if _missing(v):
        if required:
            _fail(name, "This field is required.")
        return default
    try:
        d = Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        _fail(name, "Must be a number.")
    if not d.is_finite() or abs(d) >= Decimal("100000000"):
        _fail(name, "Must be a reasonable amount.")
    return d.quantize(Decimal("0.01"))


def get_choice(data, name, choices, *, required=False, default=None):
    v = get_str(data, name, required=required, max_len=50, default=None)
    if v is None:
        return default
    if v not in choices:
        _fail(name, "Must be one of: " + ", ".join(choices) + ".")
    return v


def get_bool(data, name, default=False):
    v = data.get(name)
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def get_date(data, name, *, required=False):
    v = get_str(data, name, required=required, max_len=10, default=None)
    if v is None:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        _fail(name, "Must be a date (YYYY-MM-DD).")


def get_time(data, name, *, required=False):
    v = get_str(data, name, required=required, max_len=8, default=None)
    if v is None:
        return None
    try:
        return time.fromisoformat(v)
    except ValueError:
        _fail(name, "Must be a time (HH:MM).")
