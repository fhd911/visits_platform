from datetime import date

from django.test import TestCase

from academic.models import AcademicYear, Holiday, StudyWeek, Term


class CalendarTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(name="1448", start_date=date(2026, 8, 23), end_date=date(2027, 6, 1),
                                                is_current=True)
        self.term = Term.objects.create(year=self.year, name="ف1", start_date=date(2026, 8, 25), end_date=date(2026, 9, 30))

    def test_generate_weeks_sunday_to_thursday(self):
        n = self.term.generate_weeks()
        self.assertEqual(n, 6)
        first = StudyWeek.objects.first()
        self.assertEqual(first.start_date, date(2026, 8, 23))
        self.assertEqual(first.end_date, date(2026, 8, 27))
        self.assertEqual(first.number, 1)
        self.assertEqual(self.term.generate_weeks(), 0)  # idempotent

    def test_workdays_and_holidays(self):
        self.term.generate_weeks()
        Holiday.objects.create(name="اليوم الوطني", start_date=date(2026, 9, 23), end_date=date(2026, 9, 23))
        week = StudyWeek.for_date(date(2026, 9, 23))
        days = week.workdays()
        self.assertEqual([d["name"] for d in days], ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس"])
        self.assertEqual([d["holiday"] for d in days], [False, False, False, True, False])

    def test_for_date_on_weekend_maps_to_week(self):
        self.term.generate_weeks()
        self.assertEqual(StudyWeek.for_date(date(2026, 8, 28)).number, 1)  # الجمعة

    def test_single_current_year(self):
        y2 = AcademicYear.objects.create(name="1449", start_date=date(2027, 8, 1), end_date=date(2028, 6, 1), is_current=True)
        self.year.refresh_from_db()
        self.assertFalse(self.year.is_current)
        self.assertEqual(AcademicYear.current(), y2)
