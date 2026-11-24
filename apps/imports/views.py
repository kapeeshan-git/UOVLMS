from apps.accounts.models import ADMIN
from apps.audit.services import log as audit_log
from apps.core.errors import ApiError
from apps.core.http import api, get_bool, get_choice, paginate

from .models import ImportRun
from .services import COLUMNS, run_import


def run_dict(r):
    return {"id": r.id, "kind": r.kind, "file_name": r.file_name, "dry_run": r.dry_run, "status": r.status,
            "summary": r.summary, "created_by": r.created_by.username, "created_at": r.created_at}


@api(methods=("GET", "POST"), roles=ADMIN)
def imports(request):
    if request.method == "GET":
        return {**paginate(request, ImportRun.objects.select_related("created_by"), run_dict), "columns": COLUMNS}
    kind = get_choice(request.data, "kind", ImportRun.Kind.values, required=True)
    dry_run = get_bool(request.data, "dry_run", True)
    upload = request.FILES.get("file")
    if upload is None:
        raise ApiError("VALIDATION_ERROR", "file: Choose a CSV file.", 400, {"file": "Required."})
    status, summary = run_import(kind, upload.read(), dry_run)
    run = ImportRun.objects.create(kind=kind, file_name=upload.name[:255], dry_run=dry_run, status=status,
                                   summary=summary, created_by=request.user)
    audit_log(request.user, "import.dry_run" if dry_run else "import.apply", "import_run", run.id,
              metadata={"status": status, **{k: v for k, v in summary.items() if k != "errors"}})
    return run_dict(run), 201


@api(roles=ADMIN)
def import_detail(request, pk):
    return run_dict(ImportRun.objects.select_related("created_by").get(pk=pk))
