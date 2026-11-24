import contextvars
import re
import uuid

_request_id = contextvars.ContextVar("request_id", default="")
_VALID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def current_request_id():
    return _request_id.get()


class RequestIdMiddleware:
    """Attach X-Request-ID to every request/response; audit rows and logs use the same id."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if _VALID.match(incoming) else "req_" + uuid.uuid4().hex[:20]
        request.request_id = rid
        token = _request_id.set(rid)
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
        response["X-Request-ID"] = rid
        return response
