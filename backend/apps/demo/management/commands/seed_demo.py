"""Seed realistic University of Vavuniya LMS demo data (guide section 15.1)."""
import os
from datetime import date, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Department, User
from apps.catalog.models import (
    Author,
    Book,
    BookCopy,
    Category,
    Collection,
    SectionPolicy,
)
from apps.catalog.services import set_book_authors
from apps.circulation.models import (
    CirculationRule,
    ClosedDay,
    Fine,
    FineTransaction,
    Loan,
)
from apps.circulation.services.loans import issue_copy
from apps.core import clock
from apps.core.models import IdempotencyKey, SystemState
from apps.imports.models import ImportRun
from apps.notifications.models import Job, Notification

BOOKS_SEED = [
    ("Introduction to Algorithms", "9780262046305", "005.1 COR", "MIT Press", 2022, "CS", ["Thomas H. Cormen", "Charles E. Leiserson"], "STACK", 5, "ඇල්ගොරিদම් හැඳින්වීම / الگورتھم"),
    ("Single Copy Rare Manuscript on Concurrency", "9780131103627", "005.13 KER", "Prentice Hall", 2020, "CS", ["Brian W. Kernighan"], "STACK", 1, "තනි පිටපත"),
    ("Operating System Concepts", "9781119800361", "005.43 SIL", "Wiley", 2021, "CS", ["Abraham Silberschatz"], "STACK", 3, ""),
    ("Database System Concepts", "9780078022159", "005.74 SIL", "McGraw-Hill", 2019, "CS", ["Abraham Silberschatz", "Henry F. Korth"], "STACK", 4, "දත්ත සමුදා පද්ධති"),
    ("Computer Networks", "9780132126953", "004.6 TAN", "Pearson", 2021, "CS", ["Andrew S. Tanenbaum"], "STACK", 3, ""),
    ("Artificial Intelligence: A Modern Approach", "9780134610993", "006.3 RUS", "Pearson", 2020, "CS", ["Stuart Russell", "Peter Norvig"], "STACK", 3, ""),
    ("Clean Code: A Handbook of Agile Software Craftsmanship", "9780132350884", "005.1 MAR", "Prentice Hall", 2008, "CS", ["Robert C. Martin"], "STACK", 3, ""),
    ("Design Patterns: Elements of Reusable Object-Oriented Software", "9780201633610", "005.12 GAM", "Addison-Wesley", 1994, "CS", ["Erich Gamma"], "STACK", 2, ""),
    ("Compilers: Principles, Techniques, and Tools", "9780321486813", "005.453 AHO", "Addison-Wesley", 2006, "CS", ["Alfred V. Aho"], "REF", 2, ""),
    ("Structure and Interpretation of Computer Programs", "9780262510875", "005.1 ABE", "MIT Press", 1996, "CS", ["Harold Abelson"], "STACK", 2, ""),
    ("Computer Organization and Design", "9780128201091", "004.22 PAT", "Morgan Kaufmann", 2020, "CS", ["David A. Patterson"], "STACK", 3, ""),
    ("Deep Learning", "9780262035613", "006.31 GOO", "MIT Press", 2016, "CS", ["Ian Goodfellow"], "STACK", 2, ""),
    ("Principles of Corporate Finance", "9781260013900", "658.15 BRE", "McGraw-Hill", 2020, "BIZ", ["Richard A. Brealey"], "STACK", 3, ""),
    ("Marketing Management", "9780134236933", "658.8 KOT", "Pearson", 2021, "BIZ", ["Philip Kotler"], "STACK", 3, "අලෙවිකරණ කළමනාකරණය"),
    ("Organizational Behavior", "9780134729329", "658.3 ROB", "Pearson", 2019, "BIZ", ["Stephen P. Robbins"], "STACK", 3, ""),
    ("Financial Accounting", "9781259964947", "657 LIB", "McGraw-Hill", 2020, "BIZ", ["Robert Libby"], "STACK", 2, ""),
    ("Microeconomics", "9780134184241", "338.5 PIN", "Pearson", 2018, "BIZ", ["Robert S. Pindyck"], "STACK", 2, ""),
    ("Macroeconomics", "9781319105990", "339 MAN", "Worth Publishers", 2019, "BIZ", ["N. Gregory Mankiw"], "STACK", 3, ""),
    ("Project Management: A Systems Approach", "9781119165354", "658.404 KER", "Wiley", 2017, "BIZ", ["Harold Kerzner"], "REF", 2, ""),
    ("Strategic Management", "9781260075106", "658.401 ROT", "McGraw-Hill", 2021, "BIZ", ["Frank T. Rothaermel"], "STACK", 2, ""),
    ("Molecular Biology of the Cell", "9780393884821", "571.6 ALB", "W. W. Norton", 2022, "BIO", ["Bruce Alberts"], "STACK", 3, ""),
    ("Campbell Biology", "9780135188743", "570 URR", "Pearson", 2020, "BIO", ["Lisa A. Urry"], "STACK", 4, "ජීව විද්‍යාව"),
    ("Lehninger Principles of Biochemistry", "9781319228002", "572 NEL", "W. H. Freeman", 2021, "BIO", ["David L. Nelson"], "REF", 2, ""),
    ("Ecology: Concepts and Applications", "9781260722208", "577 MOL", "McGraw-Hill", 2022, "BIO", ["Manuel C. Molles"], "STACK", 3, ""),
    ("Environmental Science: Earth as a Living Planet", "9781118427323", "363.7 BOT", "Wiley", 2014, "BIO", ["Daniel B. Botkin"], "STACK", 2, ""),
    ("Genetics: Analysis and Principles", "9781260240856", "576.5 BRO", "McGraw-Hill", 2021, "BIO", ["Robert J. Brooker"], "STACK", 2, ""),
    ("Calculus: Early Transcendentals", "9781337613927", "515 STE", "Cengage", 2020, "MATH", ["James Stewart"], "STACK", 4, ""),
    ("Linear Algebra and Its Applications", "9780321982384", "512.5 LAY", "Pearson", 2021, "MATH", ["David C. Lay"], "STACK", 3, ""),
    ("Introduction to Probability and Statistics", "9781337554428", "519.5 MEN", "Cengage", 2019, "MATH", ["William Mendenhall"], "STACK", 3, ""),
    ("Discrete Mathematics and Its Applications", "9781259676512", "511.1 ROS", "McGraw-Hill", 2019, "MATH", ["Kenneth H. Rosen"], "STACK", 3, ""),
    ("Numerical Analysis", "9781305253667", "518 BUR", "Cengage", 2015, "MATH", ["Richard L. Burden"], "STACK", 2, ""),
    ("Differential Equations with Boundary-Value Problems", "9781305965799", "515.35 ZIL", "Cengage", 2017, "MATH", ["Dennis G. Zill"], "STACK", 2, ""),
    ("Engineering Mechanics: Dynamics", "9780133915389", "620.104 HIB", "Pearson", 2015, "ENG", ["Russell C. Hibbeler"], "STACK", 3, ""),
    ("Fundamentals of Electric Circuits", "9781260226409", "621.3192 ALE", "McGraw-Hill", 2021, "ENG", ["Charles K. Alexander"], "STACK", 3, ""),
    ("Signals and Systems", "9780138147570", "621.3822 OPP", "Prentice Hall", 1996, "ENG", ["Alan V. Oppenheim"], "STACK", 2, ""),
    ("Thermodynamics: An Engineering Approach", "9781259822674", "621.4021 CEN", "McGraw-Hill", 2019, "ENG", ["Yunus A. Cengel"], "STACK", 2, ""),
    ("Materials Science and Engineering", "9781119405498", "620.11 CAL", "Wiley", 2018, "ENG", ["William D. Callister"], "STACK", 2, ""),
    ("A History of Sri Lanka", "9780520256729", "954.93 DES", "University of California Press", 2005, "HUM", ["K. M. de Silva"], "STACK", 3, "ශ්‍රී ලංකාවේ ඉතිහාසය / இலங்கை வரலாறு"),
    ("Encyclopedia of Sri Lankan Flora & Fauna", "9789555500012", "570.95493 ENC", "National Science Foundation", 2018, "HUM", ["K. M. de Silva"], "PERM_REF", 2, ""),
    ("University of Vavuniya Charter & Historical Archive", "9789555500029", "378.5493 UOV", "UOV Press", 2021, "HUM", ["K. M. de Silva"], "PERM_REF", 2, ""),
    ("Journal of Tropical Agriculture (Bound Vol. 12)", "9789555500036", "630.5 JTA", "UOV Press", 2023, "BIO", ["Bruce Alberts"], "PERIODICAL", 2, ""),
]


class Command(BaseCommand):
    help = "Seed clean demo data for University of Vavuniya LMS (safe to re-run)."

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.environ.get("DEMO_PASSWORD", "demo1234")
        self.stdout.write("Resetting existing demo records...")

        FineTransaction.objects.all().delete()
        Fine.objects.all().delete()
        Loan.objects.all().delete()
        Job.objects.all().delete()
        Notification.objects.all().delete()
        ImportRun.objects.all().delete()
        IdempotencyKey.objects.all().delete()
        BookCopy.objects.all().delete()
        Book.objects.all().delete()
        Author.objects.all().delete()
        Category.objects.all().delete()
        Collection.objects.all().delete()
        CirculationRule.objects.all().delete()
        SectionPolicy.objects.all().delete()
        ClosedDay.objects.all().delete()

        state = SystemState.get()
        state.clock_offset_minutes = 0
        state.smtp_down = False
        state.save()

        # 1. Sections
        ref_sec = SectionPolicy.objects.create(
            code="REFERENCE",
            name="Reference Section",
            issue_start=time(8, 30),
            issue_end=time(15, 0),
            return_start=time(8, 30),
            return_end=time(16, 0),
            fine_per_day=Decimal("10.00"),
        )
        stack_sec = SectionPolicy.objects.create(
            code="STACK",
            name="Lending Stack",
            issue_start=time(8, 30),
            issue_end=time(15, 0),
            return_start=time(8, 30),
            return_end=time(16, 0),
            fine_per_day=Decimal("10.00"),
        )

        # 2. Collections
        colls = {
            "REF": Collection.objects.create(
                code="REF", name="Reference", section=ref_sec
            ),
            "STACK": Collection.objects.create(
                code="STACK", name="Lending", section=stack_sec
            ),
            "PERM_REF": Collection.objects.create(
                code="PERM_REF", name="Permanent Reference", section=None
            ),
            "PERIODICAL": Collection.objects.create(
                code="PERIODICAL", name="Bound Periodical", section=None
            ),
        }

        # 3. Circulation Rules (guide 15.1)
        student_rules = [
            (1, 1, 1, 7, 2),
            (2, 1, 1, 7, 3),
            (3, 1, 1, 7, 4),
            (4, 1, 1, 7, 4),
        ]
        for yr, ref_days, ref_max, stk_days, stk_max in student_rules:
            CirculationRule.objects.create(
                patron_category=User.Category.STUDENT,
                academic_year=yr,
                section=ref_sec,
                is_allowed=True,
                loan_period_days=ref_days,
                max_loans=ref_max,
                max_renewals=0,
                reminder_hours_before=24,
                final_reminder_hours_before=3,
            )
            CirculationRule.objects.create(
                patron_category=User.Category.STUDENT,
                academic_year=yr,
                section=stack_sec,
                is_allowed=True,
                loan_period_days=stk_days,
                max_loans=stk_max,
                max_renewals=2,
                reminder_hours_before=24,
                final_reminder_hours_before=3,
            )

        staff_rules = [
            (User.Category.ACADEMIC_PERMANENT, True, 7, 2, True, 30, 6),
            (User.Category.ACADEMIC_TEMPORARY, True, 7, 2, True, 30, 2),
            (User.Category.NON_ACADEMIC, False, 0, 0, True, 7, 2),
        ]
        for (
            cat,
            ref_ok,
            ref_days,
            ref_max,
            stk_ok,
            stk_days,
            stk_max,
        ) in staff_rules:
            CirculationRule.objects.create(
                patron_category=cat,
                academic_year=None,
                section=ref_sec,
                is_allowed=ref_ok,
                loan_period_days=ref_days,
                max_loans=ref_max,
                max_renewals=0,
                reminder_hours_before=24,
                final_reminder_hours_before=3,
            )
            CirculationRule.objects.create(
                patron_category=cat,
                academic_year=None,
                section=stack_sec,
                is_allowed=stk_ok,
                loan_period_days=stk_days,
                max_loans=stk_max,
                max_renewals=2,
                reminder_hours_before=24,
                final_reminder_hours_before=3,
            )

        # 4. Closed Days (2 sample holidays in next 60 days)
        today_d = clock.today()
        ClosedDay.objects.create(
            day=today_d + timedelta(days=5),
            reason="Poya Public Holiday",
        )
        ClosedDay.objects.create(
            day=today_d + timedelta(days=25),
            reason="University Convocation Day",
        )

        # 5. Departments & Users
        dept_ict, _ = Department.objects.get_or_create(
            name="Department of ICT",
            defaults={"faculty": "Faculty of Technological Studies"},
        )
        dept_biz, _ = Department.objects.get_or_create(
            name="Department of Business Economics",
            defaults={"faculty": "Faculty of Business Studies"},
        )
        dept_bio, _ = Department.objects.get_or_create(
            name="Department of Bio-Science",
            defaults={"faculty": "Faculty of Applied Science"},
        )
        dept_lib, _ = Department.objects.get_or_create(
            name="Main Library Administration",
            defaults={"faculty": "Library Services"},
        )

        cur_year = today_d.year
        users_spec = [
            ("admin", "Dr. S. Rajaratnam (Admin)", User.Role.ADMIN, "", None, None, dept_lib, "admin@vau.ac.lk"),
            ("librarian1", "K. Selvam (Desk 1)", User.Role.LIBRARIAN, "", None, None, dept_lib, "librarian1@vau.ac.lk"),
            ("librarian2", "M. Fernando (Desk 2)", User.Role.LIBRARIAN, "", None, None, dept_lib, "librarian2@vau.ac.lk"),
            ("student1", "Kasun Jayawardena", User.Role.MEMBER, User.Category.STUDENT, cur_year, "2026/ICT/001", dept_ict, "student1@vau.ac.lk"),
            ("student3", "Nimal Perera", User.Role.MEMBER, User.Category.STUDENT, cur_year - 2, "2024/ICT/014", dept_ict, "student3@vau.ac.lk"),
            ("lecturer1", "Prof. A.Tharmaratnam", User.Role.MEMBER, User.Category.ACADEMIC_PERMANENT, None, "STAFF/ACA/012", dept_ict, "lecturer1@vau.ac.lk"),
            ("staff1", "R. Sivakumar", User.Role.MEMBER, User.Category.NON_ACADEMIC, None, "STAFF/ADM/045", dept_biz, "staff1@vau.ac.lk"),
            ("grad1", "ThariniWijesinghe", User.Role.MEMBER, User.Category.STUDENT, cur_year - 3, "2023/BIO/008", dept_bio, "grad1@vau.ac.lk"),
        ]

        created_users = {}
        for (
            uname,
            fname,
            role,
            pcat,
            intake,
            reg,
            dept,
            email,
        ) in users_spec:
            u, _ = User.objects.update_or_create(
                username=uname,
                defaults={
                    "full_name": fname,
                    "role": role,
                    "patron_category": pcat,
                    "intake_year": intake,
                    "reg_number": reg,
                    "department": dept,
                    "email": email,
                    "status": User.Status.ACTIVE,
                    "is_active": True,
                    "is_staff": role == User.Role.ADMIN,
                    "is_superuser": role == User.Role.ADMIN,
                },
            )
            u.set_password(password)
            u.save()
            created_users[uname] = u

        # 6. Categories & Books & Copies
        cats = {
            "CS": Category.objects.create(
                code="CS", name="Computer Science & IT"
            ),
            "BIZ": Category.objects.create(
                code="BIZ", name="Business & Economics"
            ),
            "BIO": Category.objects.create(
                code="BIO", name="Biological & Environmental Sciences"
            ),
            "MATH": Category.objects.create(
                code="MATH", name="Mathematics & Statistics"
            ),
            "ENG": Category.objects.create(
                code="ENG", name="Engineering & Technology"
            ),
            "HUM": Category.objects.create(
                code="HUM", name="Sri Lankan Studies & Reference"
            ),
        }

        acc_counter = 1
        for (
            title,
            isbn,
            call_no,
            pub,
            yr,
            cat_code,
            author_list,
            coll_code,
            num_copies,
            title_alt,
        ) in BOOKS_SEED:
            book = Book.objects.create(
                title=title,
                title_alt=title_alt,
                isbn=isbn,
                call_number=call_no,
                publisher=pub,
                year=yr,
                category=cats[cat_code],
            )
            set_book_authors(book, author_list)
            for c_idx in range(num_copies):
                acc = f"A-{acc_counter:06d}"
                acc_counter += 1
                BookCopy.objects.create(
                    book=book,
                    accession_number=acc,
                    collection=colls[coll_code],
                    shelf_location=f"{cat_code}-Row-{(c_idx % 4) + 1}",
                    condition="Good",
                )

        # 7. Seed a historical returned loan with an OPEN fine for grad1 (so clearance fails initially)
        lib1 = created_users["librarian1"]
        grad1 = created_users["grad1"]
        student3 = created_users["student3"]
        now_dt = clock.now()

        grad_copy = BookCopy.objects.filter(collection=colls["STACK"]).last()
        grad_loan = Loan.objects.create(
            patron=grad1,
            copy=grad_copy,
            issued_by=lib1,
            issued_at=now_dt - timedelta(days=15),
            due_at=now_dt - timedelta(days=8),
            returned_at=now_dt - timedelta(days=4),
            status=Loan.Status.RETURNED,
            title_snapshot=grad_copy.book.title,
            accession_snapshot=grad_copy.accession_number,
            section_snapshot="STACK",
        )
        Fine.objects.create(
            loan=grad_loan,
            patron=grad1,
            days_late=4,
            rate_applied=Decimal("10.00"),
            calculated_amount=Decimal("40.00"),
            balance=Decimal("40.00"),
            status=Fine.Status.OPEN,
            created_at=now_dt - timedelta(days=4),
        )

        # 8. Issue 2 active STACK books to student3 so their portal & desk look populated
        issue_copy(
            librarian=lib1,
            patron_id=student3.id,
            accession_number="A-000001",
        )
        issue_copy(
            librarian=lib1,
            patron_id=student3.id,
            accession_number="A-000007",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Book.objects.count()} books, {BookCopy.objects.count()} copies, "
                f"and {User.objects.count()} users (password: {password})."
            )
        )
