"""Automated test suite covering guide §17.1 (Due dates, Fines, Rules, Permissions/IDOR, Idempotency, Jobs, Import)."""
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import Client, TestCase

from apps.accounts.models import User
from apps.accounts.services import academic_year_of
from apps.catalog.models import BookCopy, SectionPolicy
from apps.circulation.models import ClosedDay, Fine, Loan
from apps.circulation.services.calendar import due_date, fine_days
from apps.circulation.services.fines import check_clearance, record_fine_transaction
from apps.circulation.services.loans import issue_copy, renew_loan, return_copy
from apps.circulation.services.reminders import scan_reminders
from apps.circulation.services.rules import find_rule
from apps.core import clock
from apps.core.clock import COLOMBO
from apps.imports.services import run_import
from apps.notifications.models import Job, Notification
from apps.notifications.services import process_jobs


class LmsBusinessAndSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")

    def test_clock_rule_no_direct_timezone_now_outside_clock_module(self):
        apps_dir = Path(__file__).resolve().parent.parent / "apps"
        offenders = []
        for py in apps_dir.rglob("*.py"):
            if py.name == "clock.py":
                continue
            text = py.read_text(encoding="utf-8")
            if "timezone.now()" in text or "datetime.now()" in text:
                offenders.append(str(py))
        self.assertEqual(offenders, [])

    def test_due_date_skips_sunday_and_closed_holidays(self):
        # 2026-11-01 is a Sunday (weekday 6)
        saturday = date(2026, 10, 31)
        monday_holiday = date(2026, 11, 2)
        d = due_date(saturday, 1, {monday_holiday}, {6})
        self.assertEqual(d, date(2026, 11, 3))  # Rolls past Sunday and Monday holiday to Tuesday

    def test_fine_calculation_skips_closed_days_and_handles_same_day_late(self):
        due = datetime(2026, 10, 30, 16, 0, tzinfo=COLOMBO)  # Friday 16:00
        # Returned on time
        self.assertEqual(fine_days(due, due, set(), {6}), 0)
        # Returned 1 hour late on same due date -> 1 day
        self.assertEqual(
            fine_days(due, due + timedelta(hours=1), set(), {6}), 1
        )
        # Returned Monday across Sunday (Sunday closed) -> Saturday (1) + Monday (1) = 2 days
        monday_ret = datetime(2026, 11, 2, 10, 0, tzinfo=COLOMBO)
        self.assertEqual(fine_days(due, monday_ret, set(), {6}), 2)

    def test_academic_year_and_rule_lookup(self):
        s1 = User.objects.get(username="student1")
        s3 = User.objects.get(username="student3")
        staff = User.objects.get(username="staff1")
        today = clock.today()
        self.assertEqual(academic_year_of(s1, today), 1)
        self.assertEqual(academic_year_of(s3, today), 3)

        r1 = find_rule(s1, "STACK", today)
        r3 = find_rule(s3, "STACK", today)
        r_staff_ref = find_rule(staff, "REFERENCE", today)
        self.assertEqual(r1.max_loans, 2)
        self.assertEqual(r3.max_loans, 4)
        self.assertFalse(r_staff_ref.is_allowed)

    def test_issue_limits_and_single_active_loan_constraint(self):
        lib = User.objects.get(username="librarian1")
        s1 = User.objects.get(username="student1")  # max 2 STACK loans
        issue_copy(librarian=lib, patron_id=s1.id, accession_number="A-000002")
        issue_copy(librarian=lib, patron_id=s1.id, accession_number="A-000003")

        # 3rd STACK loan blocked
        with self.assertRaises(Exception) as ctx:
            issue_copy(
                librarian=lib, patron_id=s1.id, accession_number="A-000004"
            )
        self.assertEqual(getattr(ctx.exception, "code", ""), "LOAN_LIMIT_REACHED")

        # Issuing an already ON_LOAN copy is blocked
        with self.assertRaises(Exception) as ctx2:
            issue_copy(
                librarian=lib, patron_id=s1.id, accession_number="A-000001"
            )
        self.assertEqual(getattr(ctx2.exception, "code", ""), "COPY_NOT_AVAILABLE")

    def test_clearance_and_fine_settlement(self):
        lib = User.objects.get(username="librarian1")
        grad1 = User.objects.get(username="grad1")
        clr_before = check_clearance(grad1)
        self.assertFalse(clr_before["cleared"])

        fine = Fine.objects.get(patron=grad1, status=Fine.Status.OPEN)
        record_fine_transaction(
            lib,
            fine.id,
            {"type": "PAYMENT", "amount": "20.00", "receipt_ref": "R1"},
        )
        record_fine_transaction(
            lib,
            fine.id,
            {"type": "WAIVER", "amount": "20.00", "reason": "Approved waiver"},
        )
        clr_after = check_clearance(grad1)
        self.assertTrue(clr_after["cleared"])

    def test_permissions_idor_and_idempotency(self):
        c = Client()
        # Unauthenticated rejected
        r_unauth = c.get("/api/v1/loans/mine")
        self.assertEqual(r_unauth.status_code, 401)

        # Login as student1
        c.force_login(User.objects.get(username="student1"))
        # Member cannot access admin or desk endpoints
        self.assertEqual(c.get("/api/v1/admin/audit").status_code, 403)
        self.assertEqual(c.get("/api/v1/patrons").status_code, 403)

        # IDOR check: student1 cannot renew student3's active loan
        s3_loan = Loan.objects.filter(
            patron__username="student3", status="ACTIVE"
        ).first()
        r_idor = c.post(
            f"/api/v1/loans/{s3_loan.id}/renew",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="idem-idor-test-1",
        )
        self.assertEqual(r_idor.status_code, 404)

        # Login as librarian1 and test Idempotency-Key replay & conflict
        c.force_login(User.objects.get(username="librarian1"))
        s1 = User.objects.get(username="student1")
        body1 = json.dumps({"patron_id": s1.id, "accession_number": "A-000002"})
        res1 = c.post(
            "/api/v1/loans",
            data=body1,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="idem-key-100",
        )
        self.assertEqual(res1.status_code, 201)

        # Same key + same body -> replays 201
        res2 = c.post(
            "/api/v1/loans",
            data=body1,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="idem-key-100",
        )
        self.assertEqual(res2.status_code, 201)
        self.assertEqual(res2["Idempotent-Replay"], "true")

        # Same key + different body -> 409 IDEMPOTENCY_CONFLICT
        body_diff = json.dumps(
            {"patron_id": s1.id, "accession_number": "A-000003"}
        )
        res3 = c.post(
            "/api/v1/loans",
            data=body_diff,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="idem-key-100",
        )
        self.assertEqual(res3.status_code, 409)
        self.assertEqual(res3.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")

    def test_csv_import_dry_run_and_idempotent_apply(self):
        admin = User.objects.get(username="admin")
        csv_data = (
            "accession_number,title,authors,isbn,call_number,publisher,year,category_code,collection_code,shelf_location\n"
            "A-009991,Test Import Book,Dr. Author,9781111111111,005.9 TST,UOV,2024,CS,STACK,CS-1\n"
        )
        # Dry run writes nothing
        run1 = run_import(
            admin, kind="BOOKS_COPIES", csv_text=csv_data, dry_run=True
        )
        self.assertEqual(run1.status, "VALIDATED")
        self.assertEqual(run1.summary["new"], 1)
        self.assertFalse(
            BookCopy.objects.filter(accession_number="A-009991").exists()
        )

        # Apply writes the copy
        run2 = run_import(
            admin, kind="BOOKS_COPIES", csv_text=csv_data, dry_run=False
        )
        self.assertEqual(run2.status, "APPLIED")
        self.assertTrue(
            BookCopy.objects.filter(accession_number="A-009991").exists()
        )

        # Re-applying the exact same CSV is a no-op (skipped=1)
        run3 = run_import(
            admin, kind="BOOKS_COPIES", csv_text=csv_data, dry_run=False
        )
        self.assertEqual(run3.summary["new"], 0)
        self.assertEqual(run3.summary["skipped"], 1)
