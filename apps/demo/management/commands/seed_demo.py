"""python manage.py seed_demo [--reset]  (guide 15.1). All values are proposed seeds [DECISION]."""
import os
from datetime import time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Department, User
from apps.audit.models import AuditEvent
from apps.catalog.models import Author, Book, BookAuthor, BookCopy, Category, Collection, SectionPolicy
from apps.circulation.models import CirculationRule, ClosedDay, Fine, FineTransaction, Loan
from apps.core import clock
from apps.core.models import IdempotencyKey, SystemState
from apps.imports.models import ImportRun
from apps.notifications.models import Job, Notification

CATEGORIES = [("CS", "Computer Science"), ("MATH", "Mathematics"), ("BUS", "Business & Management"),
              ("ENG", "Engineering"), ("LIT", "Languages & Literature"), ("SCI", "Natural Sciences")]

BOOKS = [  # title, authors, category, year
    ("Introduction to Algorithms", "Thomas H. Cormen; Charles E. Leiserson", "CS", 2009),
    ("Operating Systems Concepts", "Abraham Silberschatz; Peter B. Galvin", "CS", 2018),
    ("Computer Networks", "Andrew S. Tanenbaum", "CS", 2010),
    ("Database System Concepts", "Abraham Silberschatz; Henry F. Korth", "CS", 2019),
    ("Artificial Intelligence: A Modern Approach", "Stuart Russell; Peter Norvig", "CS", 2020),
    ("Clean Code", "Robert C. Martin", "CS", 2008),
    ("The Pragmatic Programmer", "Andrew Hunt; David Thomas", "CS", 2019),
    ("Structure and Interpretation of Computer Programs", "Harold Abelson; Gerald Jay Sussman", "CS", 1996),
    ("Computer Organization and Design", "David A. Patterson; John L. Hennessy", "CS", 2017),
    ("Design Patterns", "Erich Gamma; Richard Helm", "CS", 1994),
    ("Linear Algebra and Its Applications", "Gilbert Strang", "MATH", 2016),
    ("Calculus: Early Transcendentals", "James Stewart", "MATH", 2015),
    ("Discrete Mathematics and Its Applications", "Kenneth H. Rosen", "MATH", 2018),
    ("Probability and Statistics for Engineers", "Ronald E. Walpole", "MATH", 2016),
    ("Numerical Analysis", "Richard L. Burden", "MATH", 2015),
    ("Abstract Algebra", "David S. Dummit", "MATH", 2004),
    ("Principles of Marketing", "Philip Kotler; Gary Armstrong", "BUS", 2020),
    ("Management", "Stephen P. Robbins", "BUS", 2017),
    ("Financial Accounting", "Jerry J. Weygandt", "BUS", 2018),
    ("Principles of Economics", "N. Gregory Mankiw", "BUS", 2020),
    ("Organizational Behavior", "Stephen P. Robbins", "BUS", 2018),
    ("Business Research Methods", "Alan Bryman", "BUS", 2015),
    ("Engineering Mechanics: Statics", "R. C. Hibbeler", "ENG", 2016),
    ("Fundamentals of Electric Circuits", "Charles K. Alexander; Matthew Sadiku", "ENG", 2016),
    ("Signals and Systems", "Alan V. Oppenheim", "ENG", 1996),
    ("Digital Design", "M. Morris Mano", "ENG", 2017),
    ("Thermodynamics: An Engineering Approach", "Yunus A. Cengel", "ENG", 2018),
    ("Fluid Mechanics", "Frank M. White", "ENG", 2015),
    ("A History of Sri Lanka", "K. M. de Silva", "LIT", 2005),
    ("English Grammar in Use", "Raymond Murphy", "LIT", 2019),
    ("The Elements of Style", "William Strunk Jr.; E. B. White", "LIT", 1999),
    ("Madol Doova", "Martin Wickramasinghe", "LIT", 1947),
    ("Tamil Literature: An Introduction", "Kamil Zvelebil", "LIT", 1974),
    ("Academic Writing for Graduate Students", "John M. Swales", "LIT", 2012),
    ("Campbell Biology", "Lisa A. Urry; Michael L. Cain", "SCI", 2020),
    ("University Physics", "Hugh D. Young; Roger A. Freedman", "SCI", 2019),
    ("Organic Chemistry", "Paula Yurkanis Bruice", "SCI", 2016),
    ("Principles of Biochemistry", "David L. Nelson; Michael M. Cox", "SCI", 2017),
    ("Environmental Science", "G. Tyler Miller", "SCI", 2018),
    ("Concepts of Genetics", "William S. Klug", "SCI", 2019),
]

# (category, year, section, allowed, days, max_loans, max_renewals)
RULES = [
    ("STUDENT", 1, "REFERENCE", True, 1, 1, 0), ("STUDENT", 1, "STACK", True, 7, 2, 2),
    ("STUDENT", 2, "REFERENCE", True, 1, 1, 0), ("STUDENT", 2, "STACK", True, 7, 3, 2),
    ("STUDENT", 3, "REFERENCE", True, 1, 1, 0), ("STUDENT", 3, "STACK", True, 7, 4, 2),
    ("STUDENT", 4, "REFERENCE", True, 1, 1, 0), ("STUDENT", 4, "STACK", True, 7, 4, 2),
    ("ACADEMIC_PERMANENT", None, "REFERENCE", True, 7, 2, 0), ("ACADEMIC_PERMANENT", None, "STACK", True, 30, 6, 2),
    ("ACADEMIC_TEMPORARY", None, "REFERENCE", True, 7, 2, 0), ("ACADEMIC_TEMPORARY", None, "STACK", True, 30, 2, 2),
    ("NON_ACADEMIC", None, "REFERENCE", False, 0, 0, 0), ("NON_ACADEMIC", None, "STACK", True, 7, 2, 2),
]


class Command(BaseCommand):
    help = "Load demo data (sections, rules, catalog, users, calendar)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete ALL existing data first.")

    def handle(self, *args, reset=False, **options):
        if User.objects.exists() and not reset:
            raise CommandError("Data already exists. Use --reset to wipe and reseed (destroys all data).")
        password = os.environ.get("DEMO_PASSWORD") or "demo1234"
        with transaction.atomic():
            if reset:
                self._wipe()
            self._seed(password)
        self.stdout.write(self.style.SUCCESS(f"Demo data loaded. Log in as admin / librarian1 / student3 with password '{password}'."))

    def _wipe(self):
        for model in (FineTransaction, Fine, Loan, Notification, Job, AuditEvent, ImportRun, IdempotencyKey,
                      BookCopy, BookAuthor, Book, Author, Category, Collection, CirculationRule, ClosedDay,
                      SectionPolicy, User, Department, SystemState):
            model.objects.all().delete()

    def _seed(self, password):
        today = clock.today()
        SystemState.objects.get_or_create(pk=1)

        hours = dict(issue_start=time(8, 30), issue_end=time(15, 0), return_start=time(8, 30), return_end=time(16, 0))
        ref = SectionPolicy.objects.create(code="REFERENCE", name="Reference", fine_per_day=Decimal("10.00"), **hours)
        stack = SectionPolicy.objects.create(code="STACK", name="Stack (lending)", fine_per_day=Decimal("10.00"), **hours)
        colls = {
            "REF": Collection.objects.create(code="REF", name="Reference", section=ref),
            "LEND": Collection.objects.create(code="LEND", name="Lending", section=stack),
            "PREF": Collection.objects.create(code="PREF", name="Permanent Reference", section=None),
            "BPER": Collection.objects.create(code="BPER", name="Bound Periodical", section=None),
        }
        for cat, year, sec, allowed, days, max_loans, renewals in RULES:
            CirculationRule.objects.create(patron_category=cat, academic_year=year, section_id=sec, is_allowed=allowed,
                                           loan_period_days=days, max_loans=max_loans, max_renewals=renewals,
                                           reminder_hours_before=24, final_reminder_hours_before=3)

        cats = {code: Category.objects.create(code=code, name=name) for code, name in CATEGORIES}
        authors = {}
        accession = 0
        copies_plan = [1, 5] + [2, 3, 2] * 13  # book 0: single copy; book 1: five copies
        for i, (title, names, cat, year) in enumerate(BOOKS):
            book = Book.objects.create(title=title, isbn=f"978{9550000000 + i * 7919:010d}"[:13], category=cats[cat],
                                       call_number=f"{cat} {100 + i}.{i % 9}", publisher="Demo Press", year=year)
            for name in [n.strip() for n in names.split(";")]:
                author = authors.get(name) or Author.objects.create(name=name)
                authors[name] = author
                BookAuthor.objects.create(book=book, author=author)
            for c in range(copies_plan[i]):
                accession += 1
                if i % 10 == 9 and c == 0:
                    coll = colls["PREF"]          # a few in-library-only copies
                elif i % 4 == 3 and c == 0:
                    coll = colls["REF"]
                else:
                    coll = colls["LEND"]
                BookCopy.objects.create(book=book, accession_number=f"A-{accession:06d}", collection=coll,
                                        shelf_location=f"Row {1 + i // 8}, Shelf {1 + i % 8}")

        ict = Department.objects.create(name="Information and Communication Technology", faculty="Technological Studies")
        bus = Department.objects.create(name="Business Economics", faculty="Business Studies")

        def user(username, full_name, role=User.Role.MEMBER, **extra):
            u = User(username=username, full_name=full_name, role=role, email=f"{username}@demo.vau.ac.lk", **extra)
            u.set_password(password)
            u.save()
            return u

        user("admin", "System Administrator", User.Role.ADMIN, is_staff=True, is_superuser=True)
        user("librarian1", "Desk Librarian One", User.Role.LIBRARIAN)
        user("librarian2", "Desk Librarian Two", User.Role.LIBRARIAN)
        y = today.year if (today.month, today.day) >= (1, 1) else today.year - 1
        user("student1", "Kavindi Jayasinghe", reg_number=f"{y}/ICT/001", patron_category="STUDENT", intake_year=y, department=ict)
        user("student3", "Nimal Perera", reg_number=f"{y - 2}/ICT/014", patron_category="STUDENT", intake_year=y - 2, department=ict)
        user("lecturer1", "Dr. Tharshini Sivakumar", reg_number="STF/ACA/021", patron_category="ACADEMIC_PERMANENT", department=ict)
        user("staff1", "Ravi Kumar", reg_number="STF/NA/007", patron_category="NON_ACADEMIC", department=bus)
        grad = user("grad1", "Fathima Rizna", reg_number=f"{y - 4}/BUS/030", patron_category="STUDENT", intake_year=y - 4, department=bus)

        # grad1 returned a book late: an open fine, so clearance fails until it is settled.
        lib = User.objects.get(username="librarian1")
        copy = BookCopy.objects.filter(collection=colls["LEND"]).order_by("-id").first()
        issued = clock.now() - timedelta(days=20)
        loan = Loan.objects.create(patron=grad, copy=copy, issued_by=lib, issued_at=issued, due_at=issued + timedelta(days=7),
                                   returned_at=issued + timedelta(days=10), status=Loan.Status.RETURNED,
                                   title_snapshot=copy.book.title, accession_snapshot=copy.accession_number, section_snapshot="STACK")
        Fine.objects.create(loan=loan, patron=grad, days_late=3, rate_applied=Decimal("10.00"),
                            calculated_amount=Decimal("30.00"), balance=Decimal("30.00"), created_at=loan.returned_at)

        # Two sample holidays in the next two months (weekly closure is Sunday via settings).
        for offset, reason in ((12, "Poya Day (sample)"), (40, "University holiday (sample)")):
            ClosedDay.objects.create(day=today + timedelta(days=offset), reason=reason)
