"""CSV import with dry-run (guide 8.6). Dry-run runs the real apply inside a transaction, then rolls back,
so the preview counts are exactly what a real apply would do."""
import csv
import io
import re

from django.db import transaction

from apps.accounts.models import Department, User
from apps.catalog.models import Book, BookCopy, Category, Collection
from apps.catalog.services import normalise_isbn, set_book_authors

MAX_ROWS = 5000
MAX_BYTES = 2 * 1024 * 1024
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

COLUMNS = {
    "BOOKS_COPIES": ["accession_number", "title", "isbn", "authors", "category_code", "call_number",
                     "publisher", "year", "collection_code", "shelf_location"],
    "PATRONS": ["username", "full_name", "email", "reg_number", "patron_category", "intake_year", "department"],
}
REQUIRED = {"BOOKS_COPIES": ["accession_number", "title", "collection_code"],
            "PATRONS": ["username", "full_name", "patron_category"]}


class _Rollback(Exception):
    pass


def parse_csv(raw: bytes):
    if len(raw) > MAX_BYTES:
        raise ValueError("File is larger than 2 MB.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("File must be UTF-8 encoded CSV.")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for i, row in enumerate(reader, start=2):  # row 1 is the header
        if i - 1 > MAX_ROWS:
            raise ValueError(f"Too many rows (max {MAX_ROWS}).")
        rows.append((i, {(k or "").strip(): (v or "").strip() for k, v in row.items()}))
    return reader.fieldnames or [], rows


def validate(kind, header, rows):
    errors = []
    missing = [c for c in REQUIRED[kind] if c not in header]
    if missing:
        return [{"row": 1, "column": c, "message": "Missing column."} for c in missing]
    if kind == "BOOKS_COPIES":
        collections = set(Collection.objects.values_list("code", flat=True))
        categories = set(Category.objects.values_list("code", flat=True))
        seen = set()
        for n, r in rows:
            for c in REQUIRED[kind]:
                if not r.get(c):
                    errors.append({"row": n, "column": c, "message": "Required."})
            acc = r.get("accession_number", "")
            if acc in seen:
                errors.append({"row": n, "column": "accession_number", "message": "Duplicate in file."})
            seen.add(acc)
            if len(acc) > 50 or len(r.get("title", "")) > 500:
                errors.append({"row": n, "column": "title", "message": "Too long."})
            if r.get("collection_code") and r["collection_code"] not in collections:
                errors.append({"row": n, "column": "collection_code", "message": f"Unknown collection {r['collection_code']}."})
            if r.get("category_code") and r["category_code"] not in categories:
                errors.append({"row": n, "column": "category_code", "message": f"Unknown category {r['category_code']}."})
            if r.get("year") and not (r["year"].isdigit() and 1000 <= int(r["year"]) <= 2100):
                errors.append({"row": n, "column": "year", "message": "Must be a year like 2019."})
    else:
        seen = set()
        for n, r in rows:
            for c in REQUIRED[kind]:
                if not r.get(c):
                    errors.append({"row": n, "column": c, "message": "Required."})
            if r.get("username") and not re.match(r"^[\w.@+-]{1,150}$", r["username"]):
                errors.append({"row": n, "column": "username", "message": "Invalid characters."})
            key = (r.get("reg_number") or r.get("username", "")).lower()
            if key in seen:
                errors.append({"row": n, "column": "reg_number", "message": "Duplicate in file."})
            seen.add(key)
            if r.get("patron_category") and r["patron_category"] not in User.Category.values:
                errors.append({"row": n, "column": "patron_category", "message": "Unknown category."})
            if r.get("email") and not EMAIL_RE.match(r["email"]):
                errors.append({"row": n, "column": "email", "message": "Invalid email."})
            year = r.get("intake_year", "")
            if year and not (year.isdigit() and 1990 <= int(year) <= 2100):
                errors.append({"row": n, "column": "intake_year", "message": "Must be a year."})
            if r.get("patron_category") == "STUDENT" and not year:
                errors.append({"row": n, "column": "intake_year", "message": "Required for students."})
    return errors


def _set(obj, field, value, changed):
    if getattr(obj, field) != value:
        setattr(obj, field, value)
        changed.append(field)


def _apply_books(rows):
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    collections = {c.code: c for c in Collection.objects.all()}
    categories = {c.code: c for c in Category.objects.all()}
    for _, r in rows:
        copy = BookCopy.objects.select_related("book").filter(accession_number=r["accession_number"]).first()
        isbn = normalise_isbn(r.get("isbn", ""))
        if copy:
            book = copy.book
        else:
            book = (Book.objects.filter(isbn=isbn).first() if isbn else None) or \
                Book.objects.filter(title=r["title"], call_number=r.get("call_number", "")).first()
        changed = []
        new_book = book is None
        book = book or Book()
        _set(book, "title", r["title"], changed)
        _set(book, "isbn", isbn, changed)
        _set(book, "call_number", r.get("call_number", "")[:100], changed)
        _set(book, "publisher", r.get("publisher", "")[:200], changed)
        _set(book, "year", int(r["year"]) if r.get("year") else None, changed)
        _set(book, "category", categories.get(r.get("category_code")), changed)
        if changed or new_book:
            book.save()
        names = [n.strip() for n in r.get("authors", "").split(";") if n.strip()]
        if names and sorted(names) != sorted(book.authors.values_list("name", flat=True)):
            set_book_authors(book, names)
            changed.append("authors")
        if copy is None:
            BookCopy.objects.create(book=book, accession_number=r["accession_number"],
                                    collection=collections[r["collection_code"]], shelf_location=r.get("shelf_location", "")[:100])
            counts["new"] += 1
            continue
        _set(copy, "collection", collections[r["collection_code"]], changed)
        _set(copy, "shelf_location", r.get("shelf_location", "")[:100], changed)
        if changed:
            copy.version += 1
            copy.save()
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
    return counts


def _apply_patrons(rows):
    counts = {"new": 0, "updated": 0, "unchanged": 0}
    for _, r in rows:
        user = (User.objects.filter(reg_number=r["reg_number"]).first() if r.get("reg_number") else None) or \
            User.objects.filter(username__iexact=r["username"]).first()
        changed = []
        new = user is None
        if new:
            user = User(username=r["username"], role=User.Role.MEMBER)
            user.set_unusable_password()
        dept = Department.objects.get_or_create(name=r["department"][:200])[0] if r.get("department") else None
        _set(user, "full_name", r["full_name"][:200], changed)
        _set(user, "email", r.get("email", ""), changed)
        _set(user, "reg_number", r.get("reg_number") or None, changed)
        _set(user, "patron_category", r["patron_category"], changed)
        _set(user, "intake_year", int(r["intake_year"]) if r.get("intake_year") else None, changed)
        _set(user, "department", dept, changed)
        if new:
            user.save()
            counts["new"] += 1
        elif changed:
            user.save()
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
    return counts


def run_import(kind, raw, dry_run):
    """Returns (status, summary). Nothing is written when there are errors or dry_run is True."""
    try:
        header, rows = parse_csv(raw)
    except ValueError as e:
        return "FAILED", {"errors": [{"row": 0, "column": "", "message": str(e)}], "rows": 0}
    errors = validate(kind, header, rows)
    if errors:
        return "FAILED", {"errors": errors[:500], "error_count": len(errors), "rows": len(rows)}
    apply = _apply_books if kind == "BOOKS_COPIES" else _apply_patrons
    counts = {}
    try:
        with transaction.atomic():
            counts = apply(rows)
            if dry_run:
                raise _Rollback()
    except _Rollback:
        pass
    return ("VALIDATED" if dry_run else "APPLIED"), {"errors": [], "rows": len(rows), **counts}
