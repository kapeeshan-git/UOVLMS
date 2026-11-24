import re

from django.db import connection, transaction
from django.db.models import Count, Q
from django.db.models.expressions import RawSQL

from apps.audit.services import log as audit_log
from apps.core.errors import ApiError
from apps.core.http import get_choice, get_int, get_str

from .models import Author, Book, BookAuthor, BookCopy, Category, Collection

_FT_OPERATORS = re.compile(r'[+\-><()~*"@]')


def _fulltext_query(q):
    """Turn user text into a safe BOOLEAN MODE query: every word required, as an ngram phrase."""
    words = [w for w in _FT_OPERATORS.sub(" ", q).split() if len(w) >= 2]
    return " ".join(f'+"{w}"' for w in words[:8])


def normalise_isbn(value):
    return re.sub(r"[\s\-]", "", value or "").upper()


def search_books(q="", category_id=None, available=None):
    qs = (Book.objects.select_related("category").prefetch_related("authors")
          .annotate(copy_count=Count("copies", distinct=True),
                    available_count=Count("copies", filter=Q(copies__status=BookCopy.Status.AVAILABLE), distinct=True)))
    q = (q or "").strip()[:200]
    if q:
        cond = Q(isbn=normalise_isbn(q)) | Q(call_number__istartswith=q) | Q(copies__accession_number=q)
        ft = _fulltext_query(q) if connection.vendor == "mysql" else ""
        if ft:  # FULLTEXT ngram index (guide 6.7); the term is always a bound parameter
            cond |= Q(id__in=RawSQL(
                "SELECT id FROM catalog_book WHERE MATCH(title, title_alt) AGAINST (%s IN BOOLEAN MODE)", [ft]))
            cond |= Q(id__in=RawSQL(
                "SELECT ba.book_id FROM catalog_bookauthor ba JOIN catalog_author a ON a.id = ba.author_id "
                "WHERE MATCH(a.name) AGAINST (%s IN BOOLEAN MODE)", [ft]))
        elif connection.vendor == "mysql":
            cond |= Q(title__istartswith=q)  # 1-character queries are below the ngram token size
        else:
            cond |= Q(title__icontains=q) | Q(title_alt__icontains=q) | Q(authors__name__icontains=q)
        qs = qs.filter(id__in=Book.objects.filter(cond).values("id"))
    if category_id:
        qs = qs.filter(category_id=category_id)
    if available:
        qs = qs.filter(available_count__gt=0)
    return qs.order_by("title", "id")


def _author_names(value):
    if isinstance(value, list):
        names = [str(n) for n in value]
    else:
        names = re.split(r"[;\n]", str(value or ""))
    return [n.strip()[:200] for n in names if n and n.strip()][:20]


def set_book_authors(book, names):
    authors = []
    for name in names:
        author = Author.objects.filter(name=name).first() or Author.objects.create(name=name)
        authors.append(author)
    BookAuthor.objects.filter(book=book).exclude(author__in=authors).delete()
    existing = set(BookAuthor.objects.filter(book=book).values_list("author_id", flat=True))
    BookAuthor.objects.bulk_create([BookAuthor(book=book, author=a) for a in authors if a.id not in existing])


def _book_fields(book, data, creating):
    if creating or "title" in data:
        book.title = get_str(data, "title", required=True, max_len=500)
    for field, max_len in (("title_alt", 500), ("call_number", 100), ("publisher", 200)):
        if creating or field in data:
            setattr(book, field, get_str(data, field, max_len=max_len))
    if creating or "isbn" in data:
        book.isbn = normalise_isbn(get_str(data, "isbn", max_len=20))
    if creating or "year" in data:
        book.year = get_int(data, "year", min_value=1000, max_value=2100)
    if creating or "category_id" in data:
        cat_id = get_int(data, "category_id")
        if cat_id and not Category.objects.filter(pk=cat_id).exists():
            raise ApiError("VALIDATION_ERROR", "category_id: Unknown category.", 400, {"category_id": "Unknown category."})
        book.category_id = cat_id


@transaction.atomic
def create_book(actor, data):
    book = Book()
    _book_fields(book, data, creating=True)
    book.save()
    set_book_authors(book, _author_names(data.get("authors")))
    audit_log(actor, "book.create", "book", book.id, metadata={"title": book.title})
    return book


@transaction.atomic
def update_book(actor, book, data):
    _book_fields(book, data, creating=False)
    book.save()
    if "authors" in data:
        set_book_authors(book, _author_names(data.get("authors")))
    audit_log(actor, "book.update", "book", book.id, metadata={k: str(v)[:100] for k, v in data.items()})
    return book


def _collection(data, required):
    coll_id = get_int(data, "collection_id", required=required)
    if coll_id is None:
        return None
    coll = Collection.objects.filter(pk=coll_id).first()
    if not coll:
        raise ApiError("VALIDATION_ERROR", "collection_id: Unknown collection.", 400, {"collection_id": "Unknown collection."})
    return coll


@transaction.atomic
def create_copy(actor, data):
    book = Book.objects.filter(pk=get_int(data, "book_id", required=True)).first()
    if not book:
        raise ApiError("VALIDATION_ERROR", "book_id: Unknown book.", 400, {"book_id": "Unknown book."})
    accession = get_str(data, "accession_number", required=True, max_len=50)
    if BookCopy.objects.filter(accession_number=accession).exists():
        raise ApiError("VALIDATION_ERROR", "accession_number: Already exists.", 400, {"accession_number": "Already exists."})
    copy = BookCopy.objects.create(
        book=book, accession_number=accession, collection=_collection(data, True),
        shelf_location=get_str(data, "shelf_location", max_len=100), condition=get_str(data, "condition", max_len=100),
    )
    audit_log(actor, "copy.create", "copy", copy.id, metadata={"accession": accession, "book_id": book.id})
    return copy


@transaction.atomic
def update_copy(actor, copy_id, data):
    copy = BookCopy.objects.select_for_update().get(pk=copy_id)
    if "collection_id" in data:
        copy.collection = _collection(data, True)
    for field in ("shelf_location", "condition"):
        if field in data:
            setattr(copy, field, get_str(data, field, max_len=100))
    copy.version += 1
    copy.save()
    audit_log(actor, "copy.update", "copy", copy.id, metadata={k: str(v)[:100] for k, v in data.items()})
    return copy


# Manual status changes (guide 7.1). ON_LOAN / LOST-from-loan only happen through circulation.
MANUAL_TRANSITIONS = {
    BookCopy.Status.AVAILABLE: {BookCopy.Status.IN_REPAIR, BookCopy.Status.WITHDRAWN},
    BookCopy.Status.IN_REPAIR: {BookCopy.Status.AVAILABLE, BookCopy.Status.WITHDRAWN},
    BookCopy.Status.LOST: {BookCopy.Status.AVAILABLE},
}


@transaction.atomic
def set_copy_status(actor, copy_id, data):
    status = get_choice(data, "status", BookCopy.Status.values, required=True)
    reason = get_str(data, "reason", max_len=500)
    copy = BookCopy.objects.select_for_update().get(pk=copy_id)
    if status not in MANUAL_TRANSITIONS.get(copy.status, set()):
        raise ApiError("INVALID_STATUS_CHANGE", f"Cannot change a copy from {copy.status} to {status}.", 409)
    old = copy.status
    copy.status = status
    copy.version += 1
    copy.save(update_fields=["status", "version"])
    audit_log(actor, "copy.status", "copy", copy.id, reason=reason, metadata={"from": old, "to": status})
    return copy
