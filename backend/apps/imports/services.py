"""CSV dry-run validation and transactional apply (guide 8.6)."""
import csv
import io
import re

from django.conf import settings
from django.db import transaction

from apps.accounts.models import Department, User
from apps.audit.services import log as audit_log
from apps.catalog.models import Book, BookCopy, Category, Collection
from apps.catalog.services import normalise_isbn, set_book_authors
from apps.core import clock
from apps.core.errors import ApiError

from .models import ImportRun

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BOOK_HEADERS = {
    "accession_number",
    "title",
    "authors",
    "category_code",
    "collection_code",
}
PATRON_HEADERS = {"username", "full_name", "patron_category"}


def _parse_csv(csv_text, required_headers):
    if not csv_text or not csv_text.strip():
        raise ApiError("VALIDATION_ERROR", "CSV file is empty.", 400)
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    headers = {h.strip() for h in (reader.fieldnames or []) if h}
    missing = required_headers - headers
    if missing:
        raise ApiError(
            "VALIDATION_ERROR",
            f"Missing required CSV columns: {', '.join(sorted(missing))}.",
            400,
        )
    rows = []
    for idx, raw in enumerate(reader, start=2):
        cleaned = {
            (k or "").strip(): (v or "").strip() for k, v in raw.items() if k
        }
        if any(cleaned.values()):
            rows.append((idx, cleaned))
    if not rows:
        raise ApiError("VALIDATION_ERROR", "CSV contains no data rows.", 400)
    if len(rows) > 2000:
        raise ApiError("VALIDATION_ERROR", "Maximum 2000 rows per import.", 400)
    return rows


def _process_books_copies(rows, apply_changes=False):
    categories = {c.code.upper(): c for c in Category.objects.all()}
    collections = {c.code.upper(): c for c in Collection.objects.all()}
    errors = []
    seen_accessions = set()
    created, updated, skipped = 0, 0, 0

    for row_num, r in rows:
        acc = r.get("accession_number", "")
        title = r.get("title", "")
        authors_raw = r.get("authors", "")
        cat_code = r.get("category_code", "").upper()
        coll_code = r.get("collection_code", "").upper()
        year_str = r.get("year", "")
        isbn = normalise_isbn(r.get("isbn", ""))
        call_number = r.get("call_number", "")
        publisher = r.get("publisher", "")
        shelf = r.get("shelf_location", "")

        if not acc:
            errors.append(
                {
                    "row": row_num,
                    "column": "accession_number",
                    "message": "Accession number is required.",
                }
            )
        elif acc.upper() in seen_accessions:
            errors.append(
                {
                    "row": row_num,
                    "column": "accession_number",
                    "message": f"Duplicate accession '{acc}' in file.",
                }
            )
        else:
            seen_accessions.add(acc.upper())

        if not title:
            errors.append(
                {
                    "row": row_num,
                    "column": "title",
                    "message": "Title is required.",
                }
            )
        if cat_code and cat_code not in categories:
            errors.append(
                {
                    "row": row_num,
                    "column": "category_code",
                    "message": f"Unknown category code '{cat_code}'.",
                }
            )
        if not coll_code or coll_code not in collections:
            errors.append(
                {
                    "row": row_num,
                    "column": "collection_code",
                    "message": f"Unknown collection code '{coll_code}'.",
                }
            )
        year = None
        if year_str:
            try:
                year = int(year_str)
                if not (1000 <= year <= 2100):
                    raise ValueError
            except ValueError:
                errors.append(
                    {
                        "row": row_num,
                        "column": "year",
                        "message": "Year must be between 1000 and 2100.",
                    }
                )

        if errors:
            continue

        existing_copy = (
            BookCopy.objects.select_related("book")
            .filter(accession_number=acc)
            .first()
        )
        cat = categories.get(cat_code)
        coll = collections[coll_code]
        author_list = [
            a.strip() for a in re.split(r"[;|]", authors_raw) if a.strip()
        ]

        if existing_copy:
            book = existing_copy.book
            same = (
                book.title == title
                and book.isbn == isbn
                and book.call_number == call_number
                and book.category_id == (cat.id if cat else None)
                and existing_copy.collection_id == coll.id
                and existing_copy.shelf_location == shelf
            )
            if same:
                skipped += 1
            else:
                updated += 1
                if apply_changes:
                    book.title = title
                    book.isbn = isbn
                    book.call_number = call_number
                    book.publisher = publisher or book.publisher
                    book.year = year or book.year
                    book.category = cat
                    book.save()
                    if author_list:
                        set_book_authors(book, author_list)
                    existing_copy.collection = coll
                    existing_copy.shelf_location = shelf
                    existing_copy.version += 1
                    existing_copy.save()
        else:
            created += 1
            if apply_changes:
                book = None
                if isbn:
                    book = Book.objects.filter(isbn=isbn).first()
                if not book:
                    book = Book.objects.filter(
                        title=title, call_number=call_number
                    ).first()
                if not book:
                    book = Book.objects.create(
                        title=title,
                        isbn=isbn,
                        call_number=call_number,
                        publisher=publisher,
                        year=year,
                        category=cat,
                    )
                    if author_list:
                        set_book_authors(book, author_list)
                BookCopy.objects.create(
                    book=book,
                    accession_number=acc,
                    collection=coll,
                    shelf_location=shelf,
                    condition="Good",
                )

    return {
        "total_rows": len(rows),
        "new": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


def _process_patrons(rows, apply_changes=False):
    departments = {d.name.upper(): d for d in Department.objects.all()}
    errors = []
    seen_usernames = set()
    seen_regs = set()
    created, updated, skipped = 0, 0, 0

    for row_num, r in rows:
        username = r.get("username", "")
        full_name = r.get("full_name", "")
        reg_number = r.get("reg_number", "") or None
        email = r.get("email", "")
        cat = r.get("patron_category", "").upper()
        intake_str = r.get("intake_year", "")
        dep_name = r.get("department", "")

        if not username:
            errors.append(
                {
                    "row": row_num,
                    "column": "username",
                    "message": "Username is required.",
                }
            )
        elif username.lower() in seen_usernames:
            errors.append(
                {
                    "row": row_num,
                    "column": "username",
                    "message": f"Duplicate username '{username}' in file.",
                }
            )
        else:
            seen_usernames.add(username.lower())

        if reg_number:
            if reg_number.upper() in seen_regs:
                errors.append(
                    {
                        "row": row_num,
                        "column": "reg_number",
                        "message": f"Duplicate reg_number '{reg_number}' in file.",
                    }
                )
            else:
                seen_regs.add(reg_number.upper())

        if not full_name:
            errors.append(
                {
                    "row": row_num,
                    "column": "full_name",
                    "message": "Full name is required.",
                }
            )
        if cat not in User.Category.values:
            errors.append(
                {
                    "row": row_num,
                    "column": "patron_category",
                    "message": f"Must be one of {', '.join(User.Category.values)}.",
                }
            )
        if email and not EMAIL_RE.match(email):
            errors.append(
                {
                    "row": row_num,
                    "column": "email",
                    "message": "Invalid email address.",
                }
            )
        intake_year = None
        if intake_str:
            try:
                intake_year = int(intake_str)
                if not (1990 <= intake_year <= 2100):
                    raise ValueError
            except ValueError:
                errors.append(
                    {
                        "row": row_num,
                        "column": "intake_year",
                        "message": "Invalid intake_year.",
                    }
                )
        elif cat == User.Category.STUDENT:
            errors.append(
                {
                    "row": row_num,
                    "column": "intake_year",
                    "message": "intake_year is required for STUDENT.",
                }
            )

        if errors:
            continue

        dep = departments.get(dep_name.upper()) if dep_name else None
        if dep_name and not dep and apply_changes:
            dep = Department.objects.create(name=dep_name)
            departments[dep_name.upper()] = dep

        existing = (
            User.objects.filter(reg_number__iexact=reg_number).first()
            if reg_number
            else None
        ) or User.objects.filter(username__iexact=username).first()

        if existing:
            same = (
                existing.full_name == full_name
                and existing.email == email
                and existing.patron_category == cat
                and existing.intake_year == intake_year
            )
            if same:
                skipped += 1
            else:
                updated += 1
                if apply_changes:
                    existing.full_name = full_name
                    existing.email = email
                    existing.patron_category = cat
                    existing.intake_year = intake_year
                    if dep:
                        existing.department = dep
                    existing.save()
        else:
            created += 1
            if apply_changes:
                u = User(
                    username=username,
                    full_name=full_name,
                    reg_number=reg_number,
                    email=email,
                    role=User.Role.MEMBER,
                    patron_category=cat,
                    intake_year=intake_year,
                    department=dep,
                )
                import os
                u.set_password(os.environ.get("DEMO_PASSWORD", "demo1234"))
                u.save()

    return {
        "total_rows": len(rows),
        "new": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }


def run_import(actor, *, kind, csv_text, file_name="upload.csv", dry_run=True):
    if kind not in ImportRun.Kind.values:
        raise ApiError(
            "VALIDATION_ERROR",
            f"kind: Must be one of {', '.join(ImportRun.Kind.values)}.",
            400,
        )
    headers = (
        BOOK_HEADERS
        if kind == ImportRun.Kind.BOOKS_COPIES
        else PATRON_HEADERS
    )
    rows = _parse_csv(csv_text, headers)
    processor = (
        _process_books_copies
        if kind == ImportRun.Kind.BOOKS_COPIES
        else _process_patrons
    )

    summary = processor(rows, apply_changes=False)
    has_errors = len(summary["errors"]) > 0

    if has_errors:
        status = ImportRun.Status.FAILED
    elif dry_run:
        status = ImportRun.Status.VALIDATED
    else:
        with transaction.atomic():
            summary = processor(rows, apply_changes=True)
            status = ImportRun.Status.APPLIED

    run = ImportRun.objects.create(
        kind=kind,
        file_name=file_name[:200],
        dry_run=dry_run,
        status=status,
        summary=summary,
        created_by=actor,
        created_at=clock.now(),
    )
    audit_log(
        actor,
        "import.dry_run" if dry_run else "import.apply",
        "import_run",
        run.id,
        metadata={
            "kind": kind,
            "file_name": file_name,
            "status": status,
            "new": summary["new"],
            "updated": summary["updated"],
            "skipped": summary["skipped"],
            "error_count": len(summary["errors"]),
        },
    )
    return run
