"""Pure-function tests for due dates and fines (guide 17.1)."""
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from apps.circulation.services.calendar import due_date, fine_days

C = ZoneInfo("Asia/Colombo")
SUNDAY = {6}


def at(y, m, d, hh=16, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=C)


class DueDateTests(SimpleTestCase):
    def test_normal(self):  # Mon 2 Nov 2026 + 7 = Mon 9 Nov
        self.assertEqual(due_date(date(2026, 11, 2), 7, set(), SUNDAY), date(2026, 11, 9))

    def test_lands_on_sunday_rolls_to_monday(self):  # Sat 31 Oct + 1 = Sun 1 Nov -> Mon 2 Nov
        self.assertEqual(due_date(date(2026, 10, 31), 1, set(), SUNDAY), date(2026, 11, 2))

    def test_lands_on_holiday(self):
        self.assertEqual(due_date(date(2026, 11, 2), 7, {date(2026, 11, 9)}, SUNDAY), date(2026, 11, 10))

    def test_holiday_then_sunday(self):  # Sat holiday, Sun closed -> Mon
        self.assertEqual(due_date(date(2026, 11, 6), 1, {date(2026, 11, 7)}, SUNDAY), date(2026, 11, 9))


class FineTests(SimpleTestCase):
    def test_on_time(self):
        self.assertEqual(fine_days(at(2026, 11, 9), at(2026, 11, 9, 15), set(), SUNDAY), 0)

    def test_late_same_day_counts_one(self):
        self.assertEqual(fine_days(at(2026, 11, 9), at(2026, 11, 9, 17), set(), SUNDAY), 1)

    def test_one_day_late(self):
        self.assertEqual(fine_days(at(2026, 11, 9), at(2026, 11, 10, 9), set(), SUNDAY), 1)

    def test_spanning_sunday_and_holiday(self):  # due Fri 6; Sat 7 open, Sun 8 closed, Mon 9 holiday, Tue 10 open
        self.assertEqual(fine_days(at(2026, 11, 6), at(2026, 11, 10, 10), {date(2026, 11, 9)}, SUNDAY), 2)

    def test_count_closed_days_option(self):
        self.assertEqual(fine_days(at(2026, 11, 6), at(2026, 11, 10, 10), {date(2026, 11, 9)}, SUNDAY, count_closed=True), 4)

    def test_grace_period(self):
        self.assertEqual(fine_days(at(2026, 11, 9), at(2026, 11, 9, 16, 10), set(), SUNDAY, grace=timedelta(minutes=15)), 0)


class ClockRuleTests(SimpleTestCase):
    def test_no_direct_now_outside_clock(self):
        """Guide 5.1 rule 4: core.clock is the only source of current time."""
        root = Path(__file__).resolve().parent.parent / "apps"
        offenders = [str(p) for p in root.rglob("*.py")
                     if p.name != "clock.py" and ("timezone.now(" in p.read_text(encoding="utf-8")
                                                  or "datetime.now(" in p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])
