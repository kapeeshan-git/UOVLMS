"""Concurrency tests (guide 17.2). Real threads, real MySQL; skipped on other databases."""
import threading
import unittest
from datetime import time
from decimal import Decimal

from django.db import connection
from django.test import TransactionTestCase

from apps.accounts.models import User
from apps.catalog.models import Book, BookCopy, Collection, SectionPolicy
from apps.circulation.models import CirculationRule, Loan
from apps.circulation.services.loans import issue_copy
from apps.core.errors import ApiError


def run_in_threads(*fns):
    results = [None] * len(fns)
    barrier = threading.Barrier(len(fns))

    def wrap(i, fn):
        barrier.wait()
        try:
            fn()
            results[i] = "ok"
        except ApiError as e:
            results[i] = "error:" + e.code
        finally:
            connection.close()

    threads = [threading.Thread(target=wrap, args=(i, f)) for i, f in enumerate(fns)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


@unittest.skipUnless(connection.vendor == "mysql", "needs MySQL row locks")
class ConcurrencyTests(TransactionTestCase):
    def setUp(self):
        stack = SectionPolicy.objects.create(code="STACK", name="Stack", issue_start=time(8), issue_end=time(15),
                                             return_start=time(8), return_end=time(16), fine_per_day=Decimal("10"))
        coll = Collection.objects.create(code="LEND", name="Lending", section=stack)
        CirculationRule.objects.create(patron_category="ACADEMIC_PERMANENT", section=stack, loan_period_days=7, max_loans=2)
        book = Book.objects.create(title="Concurrency")
        for i in range(1, 4):
            BookCopy.objects.create(book=book, accession_number=f"A-{i}", collection=coll)
        self.lib = User.objects.create(username="lib", full_name="Lib", role="LIBRARIAN")
        self.p1, self.p2 = [User.objects.create(username=f"p{i}", full_name=f"P{i}", patron_category="ACADEMIC_PERMANENT")
                            for i in (1, 2)]

    def test_two_librarians_issue_same_copy(self):
        results = run_in_threads(
            lambda: issue_copy(librarian=self.lib, patron_id=self.p1.id, accession_number="A-1"),
            lambda: issue_copy(librarian=self.lib, patron_id=self.p2.id, accession_number="A-1"),
        )
        self.assertEqual(sorted(results), ["error:COPY_NOT_AVAILABLE", "ok"])
        self.assertEqual(Loan.objects.filter(copy__accession_number="A-1", status="ACTIVE").count(), 1)

    def test_same_patron_at_limit_minus_one(self):
        issue_copy(librarian=self.lib, patron_id=self.p1.id, accession_number="A-1")
        results = run_in_threads(
            lambda: issue_copy(librarian=self.lib, patron_id=self.p1.id, accession_number="A-2"),
            lambda: issue_copy(librarian=self.lib, patron_id=self.p1.id, accession_number="A-3"),
        )
        self.assertEqual(sorted(results), ["error:LOAN_LIMIT_REACHED", "ok"])

    def test_db_rejects_second_active_loan(self):
        """The generated-column unique index works even if locking were bypassed."""
        from django.db import IntegrityError, transaction

        copy = BookCopy.objects.get(accession_number="A-1")
        kw = dict(copy=copy, issued_by=self.lib, issued_at="2026-01-01T00:00Z", due_at="2026-01-08T00:00Z",
                  title_snapshot="x", accession_snapshot="A-1", section_snapshot="STACK")
        Loan.objects.create(patron=self.p1, **kw)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Loan.objects.create(patron=self.p2, **kw)
        Loan.objects.update(status="RETURNED")
        Loan.objects.create(patron=self.p2, **kw)  # allowed again once the first is returned
