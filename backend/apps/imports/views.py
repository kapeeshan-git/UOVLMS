from apps.accounts.models import ADMIN
from apps.core.errors import ApiError
from apps.core.http import api, get_bool, get_str, paginate

from .models import ImportRun
from .services import run_import


def import_dict(r):
    return {
        "id": r.id,
        "kind": r.kind,
        "file_name": r.file_name,
        "dry_run": r.dry_run,
        "status": r.status,
        "summary": r.summary,
        "created_by": r.created_by.username,
        "created_at": r.created_at,
    }


@api(methods=("GET", "POST"), roles=ADMIN)
def imports(request):
    if request.method == "POST":
        kind = get_str(request.data, "kind", required=True, max_len=20)
        dry_run = get_bool(request.data, "dry_run", default=True)
        file_name = get_str(
            request.data, "file_name", max_len=200, default="import.csv"
        )
        csv_text = request.data.get("csv_text", "")
        if not csv_text and request.FILES.get("file"):
            uploaded = request.FILES["file"]
            file_name = uploaded.name
            try:
                csv_text = uploaded.read().decode("utf-8")
            except UnicodeDecodeError:
                raise ApiError(
                    "VALIDATION_ERROR", "File must be UTF-8 encoded CSV.", 400
                )
        run = run_import(
            request.user,
            kind=kind,
            csv_text=csv_text,
            file_name=file_name,
            dry_run=dry_run,
        )
        return import_dict(run), 201
    qs = ImportRun.objects.select_related("created_by")
    return paginate(request, qs, import_dict)


@api(roles=ADMIN)
def import_detail(request, pk):
    run = ImportRun.objects.select_related("created_by").get(pk=pk)
    return import_dict(run)
