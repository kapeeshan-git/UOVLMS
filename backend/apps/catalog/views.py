from django.db import transaction

from apps.accounts.models import ADMIN, STAFF
from apps.audit.services import log as audit_log
from apps.core.errors import ApiError
from apps.core.http import api, get_decimal, get_str, get_time, paginate

from . import services
from .models import Author, Book, BookCopy, Category, Collection, SectionPolicy


def copy_dict(c):
    section = c.collection.section_id
    return {
        "id": c.id,
        "book_id": c.book_id,
        "accession_number": c.accession_number,
        "status": c.status,
        "collection": {
            "id": c.collection_id,
            "code": c.collection.code,
            "name": c.collection.name,
        },
        "section": section,
        "borrowable": section is not None,
        "shelf_location": c.shelf_location,
        "condition": c.condition,
        "version": c.version,
    }


def book_summary(b):
    return {
        "id": b.id,
        "title": b.title,
        "title_alt": b.title_alt,
        "isbn": b.isbn,
        "call_number": b.call_number,
        "publisher": b.publisher,
        "year": b.year,
        "category": (
            {"id": b.category_id, "name": b.category.name}
            if b.category_id
            else None
        ),
        "authors": [a.name for a in b.authors.all()],
        "copy_count": getattr(b, "copy_count", None),
        "available_count": getattr(b, "available_count", None),
    }


def _copies(book_id):
    return BookCopy.objects.filter(book_id=book_id).select_related("collection")


def book_detail_dict(book_id):
    book = services.search_books().get(pk=book_id)
    return {**book_summary(book), "copies": [copy_dict(c) for c in _copies(book_id)]}


@api(methods=("GET", "POST"), roles={"POST": STAFF})
def books(request):
    if request.method == "POST":
        return book_detail_dict(services.create_book(request.user, request.data).id), 201
    try:
        category_id = int(request.GET.get("category") or 0)
    except ValueError:
        category_id = 0
    qs = services.search_books(
        request.GET.get("q", ""),
        category_id,
        request.GET.get("available") in ("1", "true"),
    )
    return paginate(request, qs, book_summary)


@api(methods=("GET", "PATCH"), roles={"PATCH": STAFF})
def book_detail(request, pk):
    if request.method == "PATCH":
        services.update_book(request.user, Book.objects.get(pk=pk), request.data)
    return book_detail_dict(pk)


@api(roles=STAFF)
def book_copies(request, pk):
    return {"results": [copy_dict(c) for c in _copies(pk)]}


@api(methods=("POST",), roles=STAFF)
def copies(request):
    copy = services.create_copy(request.user, request.data)
    return (
        copy_dict(
            BookCopy.objects.select_related("collection").get(pk=copy.pk)
        ),
        201,
    )


@api(methods=("GET", "PATCH"), roles=STAFF)
def copy_detail(request, pk):
    if request.method == "PATCH":
        services.update_copy(request.user, pk, request.data)
    return copy_dict(BookCopy.objects.select_related("collection").get(pk=pk))


@api(methods=("POST",), roles=STAFF)
def copy_status(request, pk):
    services.set_copy_status(request.user, pk, request.data)
    return copy_dict(BookCopy.objects.select_related("collection").get(pk=pk))


@api(methods=("GET", "POST"), roles={"POST": STAFF})
def categories(request):
    if request.method == "POST":
        code = get_str(request.data, "code", required=True, max_len=30)
        if Category.objects.filter(code=code).exists():
            raise ApiError(
                "VALIDATION_ERROR",
                "code: Already exists.",
                400,
                {"code": "Already exists."},
            )
        c = Category.objects.create(
            code=code,
            name=get_str(request.data, "name", required=True, max_len=200),
        )
        audit_log(request.user, "category.create", "category", c.id)
        return {"id": c.id, "code": c.code, "name": c.name}, 201
    return {
        "results": [
            {"id": c.id, "code": c.code, "name": c.name}
            for c in Category.objects.all()
        ]
    }


@api(methods=("GET", "POST"), roles={"POST": STAFF})
def authors(request):
    if request.method == "POST":
        a = Author.objects.create(
            name=get_str(request.data, "name", required=True, max_len=200),
            biography=get_str(request.data, "biography", max_len=5000),
        )
        audit_log(request.user, "author.create", "author", a.id)
        return {"id": a.id, "name": a.name}, 201
    qs = Author.objects.all()
    q = request.GET.get("q", "").strip()[:100]
    if q:
        qs = qs.filter(name__icontains=q)
    return paginate(
        request, qs, lambda a: {"id": a.id, "name": a.name}, default_size=50
    )


@api(methods=("GET", "POST"), roles={"POST": STAFF})
def collections(request):
    if request.method == "POST":
        code = get_str(request.data, "code", required=True, max_len=30)
        section = get_str(request.data, "section_code", max_len=20) or None
        if section and not SectionPolicy.objects.filter(pk=section).exists():
            raise ApiError(
                "VALIDATION_ERROR",
                "section_code: Unknown section.",
                400,
                {"section_code": "Unknown section."},
            )
        c = Collection.objects.create(
            code=code,
            name=get_str(request.data, "name", required=True, max_len=100),
            section_id=section,
        )
        audit_log(request.user, "collection.create", "collection", c.id)
    return {
        "results": [
            {
                "id": c.id,
                "code": c.code,
                "name": c.name,
                "section": c.section_id,
                "borrowable": c.section_id is not None,
            }
            for c in Collection.objects.all()
        ]
    }


def section_dict(s):
    return {
        "code": s.code,
        "name": s.name,
        "issue_start": s.issue_start,
        "issue_end": s.issue_end,
        "return_start": s.return_start,
        "return_end": s.return_end,
        "fine_per_day": s.fine_per_day,
    }


@api(methods=("GET", "PUT"), roles={"GET": STAFF, "PUT": ADMIN})
def admin_sections(request):
    if request.method == "PUT":
        items = request.data.get("sections")
        if not isinstance(items, list):
            raise ApiError(
                "VALIDATION_ERROR",
                "sections: Must be a list.",
                400,
                {"sections": "Must be a list."},
            )
        with transaction.atomic():
            for item in items:
                s = SectionPolicy.objects.select_for_update().get(
                    pk=get_str(item, "code", required=True, max_len=20)
                )
                for f in ("issue_start", "issue_end", "return_start", "return_end"):
                    setattr(s, f, get_time(item, f, required=True))
                fine = get_decimal(item, "fine_per_day", required=True)
                if fine < 0:
                    raise ApiError(
                        "VALIDATION_ERROR",
                        "fine_per_day: Cannot be negative.",
                        400,
                    )
                s.fine_per_day = fine
                s.name = get_str(item, "name", max_len=100) or s.name
                s.save()
                audit_log(
                    request.user,
                    "section.update",
                    "section",
                    None,
                    metadata={k: str(v) for k, v in section_dict(s).items()},
                )
    return {
        "results": [section_dict(s) for s in SectionPolicy.objects.order_by("code")]
    }
