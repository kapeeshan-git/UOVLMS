"""End-to-end API tests on seeded demo data (guide 15.2 / 17.1)."""
import json
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.catalog.models import BookCopy
from apps.circulation.models import Fine, Loan
from apps.core import clock
from apps.core.models import SystemState
from apps.notifications.models import Notification
from apps.notifications.services import process_jobs, scheduler_tick


def set_offset(minutes):
    SystemState.objects.filter(pk=1).update(clock_offset_minutes=int(minutes))


@override_settings(DEMO_CLOCK_ENABLED=True)
class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=open("nul" if __import__("os").name == "nt" else "/dev/null", "w"))

    def setUp(self):
        set_offset(0)
        self.lib = User.objects.get(username="librarian1")
        self.admin = User.objects.get(username="admin")
        self.s1 = User.objects.get(username="student1")
        self.s3 = User.objects.get(username="student3")
        self.client.force_login(self.lib)

    # helpers ---------------------------------------------------------------------------------
    def post(self, path, data=None, key=None, client=None):
        return (client or self.client).post("/api/v1" + path, data=json.dumps(data or {}), content_type="application/json",
                                            HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))

    def lend_copies(self, n):
        return list(BookCopy.objects.filter(collection__code="LEND", status="AVAILABLE").order_by("id")
                    .values_list("accession_number", flat=True)[:n])

    def issue(self, patron, accession):
        return self.post("/loans", {"patron_id": patron.id, "accession_number": accession})

    # auth ------------------------------------------------------------------------------------
    def test_login_generic_error_and_success(self):
        self.client.logout()
        r = self.client.post("/api/v1/auth/login", json.dumps({"username": "nobody", "password": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "INVALID_CREDENTIALS")
        r = self.client.post("/api/v1/auth/login", json.dumps({"username": "student3", "password": "demo1234"}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user"]["role"], "MEMBER")
        self.assertIn("X-Request-ID", r)

    # rules -----------------------------------------------------------------------------------
    def test_issue_rules(self):
        accs = self.lend_copies(5)
        for acc in accs[:4]:
            self.assertEqual(self.issue(self.s3, acc).status_code, 201)
        r = self.issue(self.s3, accs[4])
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (422, "LOAN_LIMIT_REACHED"))
        r = self.issue(self.s1, accs[0])
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (409, "COPY_NOT_AVAILABLE"))
        pref = BookCopy.objects.filter(collection__code="PREF").first().accession_number
        r = self.issue(self.s1, pref)
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (422, "COPY_NOT_BORROWABLE"))
        ref = BookCopy.objects.filter(collection__code="REF", status="AVAILABLE").first().accession_number
        r = self.issue(User.objects.get(username="staff1"), ref)
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (422, "NO_CIRCULATION_RULE"))
        r = self.issue(self.s1, "NOPE-1")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (404, "COPY_NOT_FOUND"))

    def test_student_year_limit(self):  # year 1 -> max 2 stack loans
        accs = self.lend_copies(3)
        self.assertEqual(self.issue(self.s1, accs[0]).status_code, 201)
        self.assertEqual(self.issue(self.s1, accs[1]).status_code, 201)
        self.assertEqual(self.issue(self.s1, accs[2]).json()["error"]["code"], "LOAN_LIMIT_REACHED")

    # return + fines --------------------------------------------------------------------------
    def test_late_return_fine_and_ledger(self):
        acc = self.lend_copies(1)[0]
        loan_id = self.issue(self.s3, acc).json()["id"]
        set_offset(10 * 24 * 60)
        r = self.post("/loans/return", {"accession_number": acc})
        self.assertEqual(r.status_code, 200, r.content)
        fine = r.json()["fine"]
        self.assertGreaterEqual(fine["days_late"], 1)
        self.assertEqual(Decimal(fine["calculated_amount"]), Decimal("10.00") * fine["days_late"])
        self.assertEqual(BookCopy.objects.get(accession_number=acc).status, "AVAILABLE")
        # second return of the same barcode is safe
        self.assertEqual(self.post("/loans/return", {"accession_number": acc}).json()["error"]["code"], "LOAN_NOT_ACTIVE")

        fid = fine["id"]
        r = self.post(f"/fines/{fid}/transactions", {"type": "PAYMENT", "amount": "10.00", "receipt_ref": "R1"})
        self.assertEqual(r.status_code, 201)
        r = self.post(f"/fines/{fid}/transactions", {"type": "WAIVER", "amount": r.json()["balance"]})
        self.assertEqual(r.json()["error"]["code"], "VALIDATION_ERROR")  # reason required
        bal = Fine.objects.get(pk=fid).balance
        r = self.post(f"/fines/{fid}/transactions", {"type": "WAIVER", "amount": str(bal), "reason": "First offence"})
        self.assertEqual(r.json()["status"], "SETTLED")
        r = self.post(f"/fines/{fid}/transactions", {"type": "ADJUSTMENT", "amount": "5", "reason": "x"})
        self.assertEqual(r.status_code, 403)  # adjustments are admin-only
        self.assertTrue(Loan.objects.filter(pk=loan_id, status="RETURNED").exists())

    def test_renew(self):
        acc = self.lend_copies(1)[0]
        loan = self.issue(self.s3, acc).json()
        r = self.post(f"/loans/{loan['id']}/renew")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["renewal_count"], 1)
        set_offset(30 * 24 * 60)
        self.assertEqual(self.post(f"/loans/{loan['id']}/renew").json()["error"]["code"], "LOAN_OVERDUE")
        r = self.post(f"/loans/{loan['id']}/renew", {"reason": "Staff override"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.post(f"/loans/{loan['id']}/renew", {"reason": "again"}).json()["error"]["code"],
                         "RENEWAL_LIMIT_REACHED")

    # permissions -----------------------------------------------------------------------------
    def test_permissions_and_idor(self):
        loan = self.issue(self.s3, self.lend_copies(1)[0]).json()
        self.client.force_login(self.s1)
        self.assertEqual(self.post(f"/loans/{loan['id']}/renew").status_code, 404)  # not s1's loan
        self.assertEqual(self.client.get("/api/v1/loans").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/fines").status_code, 403)
        self.assertEqual(self.client.get(f"/api/v1/loans/{loan['id']}").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/loans/mine").json()["total"], 0)
        self.client.force_login(self.lib)
        self.assertEqual(self.client.get("/api/v1/admin/audit").status_code, 403)
        self.assertEqual(self.client.put("/api/v1/admin/rules", "{}", content_type="application/json").status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get("/api/v1/books").status_code, 401)

    # idempotency -----------------------------------------------------------------------------
    def test_idempotency(self):
        acc = self.lend_copies(1)[0]
        key = str(uuid.uuid4())
        r1 = self.post("/loans", {"patron_id": self.s3.id, "accession_number": acc}, key=key)
        r2 = self.post("/loans", {"patron_id": self.s3.id, "accession_number": acc}, key=key)
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(r1.json()["id"], r2.json()["id"])
        self.assertEqual(r2["Idempotent-Replay"], "true")
        r3 = self.post("/loans", {"patron_id": self.s1.id, "accession_number": acc}, key=key)
        self.assertEqual(r3.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")
        r = self.client.post("/api/v1/loans", json.dumps({}), content_type="application/json")
        self.assertEqual(r.status_code, 400)  # header required

    # reminders + worker ----------------------------------------------------------------------
    def test_reminders_deduplicate_and_send(self):
        loan = Loan.objects.get(pk=self.issue(self.s3, self.lend_copies(1)[0]).json()["id"])
        minutes_to_final = (loan.due_at - clock.now()).total_seconds() / 60 - 120  # 2h before due
        set_offset(minutes_to_final)
        mail.outbox.clear()
        self.assertEqual(scheduler_tick()[0], 1)
        self.assertEqual(scheduler_tick()[0], 0)  # re-running is harmless
        process_jobs()
        note = Notification.objects.get(related_id=loan.id, template_id="loan_final")
        self.assertEqual(note.status, "SENT")
        self.assertEqual(len(mail.outbox), 1)

    def test_smtp_outage_then_retry(self):
        SystemState.objects.filter(pk=1).update(smtp_down=True)
        acc = self.lend_copies(1)[0]
        self.issue(self.s3, acc)
        set_offset(10 * 24 * 60)
        self.post("/loans/return", {"accession_number": acc})  # queues fine_created email
        process_jobs()
        note = Notification.objects.get(template_id="fine_created", user=self.s3)
        self.assertEqual(note.status, "QUEUED")
        from apps.notifications.models import Job
        job = Job.objects.get(payload__notification_id=note.id)
        self.assertEqual((job.status, job.error_category, job.attempts), ("PENDING", "SMTP_UNAVAILABLE", 1))
        SystemState.objects.filter(pk=1).update(smtp_down=False)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(f"/api/v1/admin/jobs/{job.id}/retry").status_code, 200)
        process_jobs()
        note.refresh_from_db()
        self.assertEqual(note.status, "SENT")

    # clearance ------------------------------------------------------------------------------
    def test_clearance(self):
        grad = User.objects.get(username="grad1")
        self.assertFalse(self.client.get(f"/api/v1/patrons/{grad.id}/clearance").json()["cleared"])
        r = self.post(f"/patrons/{grad.id}/status", {"status": "GRADUATED"})
        self.assertEqual(r.json()["error"]["code"], "CLEARANCE_FAILED")
        fine = Fine.objects.get(patron=grad)
        self.post(f"/fines/{fine.id}/transactions", {"type": "PAYMENT", "amount": "30.00"})
        self.assertTrue(self.client.get(f"/api/v1/patrons/{grad.id}/clearance").json()["cleared"])
        self.assertEqual(self.post(f"/patrons/{grad.id}/status", {"status": "GRADUATED"}).json()["status"], "GRADUATED")

    # catalog + import -----------------------------------------------------------------------
    def test_search(self):
        r = self.client.get("/api/v1/books", {"q": "Algorithms"})
        self.assertEqual(r.json()["results"][0]["title"], "Introduction to Algorithms")
        r = self.client.get("/api/v1/books", {"q": "Tanenbaum"})
        self.assertEqual(r.json()["total"], 1)

    def test_import_dry_run_and_apply_is_idempotent(self):
        self.client.force_login(self.admin)
        csv = ("accession_number,title,isbn,authors,category_code,call_number,publisher,year,collection_code,shelf_location\n"
               "B-1,New Book One,,Author X,CS,CS 1,Pub,2020,LEND,R1\n"
               "B-2,New Book Two,,Author Y;Author Z,MATH,MA 2,Pub,2021,LEND,R2\n").encode()

        def upload(dry, content=csv):
            return self.client.post("/api/v1/admin/imports", {
                "kind": "BOOKS_COPIES", "dry_run": "true" if dry else "false",
                "file": SimpleUploadedFile("books.csv", content, content_type="text/csv")}).json()

        r = upload(True)
        self.assertEqual((r["status"], r["summary"]["new"]), ("VALIDATED", 2))
        self.assertFalse(BookCopy.objects.filter(accession_number="B-1").exists())
        self.assertEqual(upload(False)["summary"]["new"], 2)
        r = upload(False)
        self.assertEqual((r["summary"]["new"], r["summary"]["updated"], r["summary"]["unchanged"]), (0, 0, 2))
        bad = upload(True, csv + b"B-3,,,,,,,abc,NOPE,\n")
        self.assertEqual(bad["status"], "FAILED")
        self.assertEqual({e["column"] for e in bad["summary"]["errors"]}, {"title", "year", "collection_code"})

    def test_demo_clock_admin_only(self):
        self.assertEqual(self.post("/admin/demo/clock", {"days": 1}).status_code, 403)
        self.client.force_login(self.admin)
        r = self.post("/admin/demo/clock", {"days": 2})
        self.assertEqual(r.json()["offset_minutes"], 2 * 24 * 60)
        self.assertGreater(clock.now() - clock.real_now(), timedelta(days=1, hours=23))
