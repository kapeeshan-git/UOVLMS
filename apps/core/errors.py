class ApiError(Exception):
    """A typed business/API error rendered as {"error": {...}} (guide 10.4)."""

    def __init__(self, code, message, status=400, fields=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.fields = fields or {}

    def payload(self, request_id=""):
        return {"error": {"code": self.code, "message": self.message, "fields": self.fields, "request_id": request_id}}


def forbidden(message="You do not have permission to do this."):
    return ApiError("FORBIDDEN", message, 403)


def not_found(message="Not found."):
    return ApiError("NOT_FOUND", message, 404)
