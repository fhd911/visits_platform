from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from org.models import SchoolAssignment
from org.testing import World


class OrgTests(TestCase):
    def setUp(self):
        self.w = World(items=1)

    def test_overlapping_assignment_rejected(self):
        a = SchoolAssignment(supervisor=self.w.sup, school=self.w.school, start_date=self.w.today)
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_only_supervisors_can_be_assigned(self):
        a = SchoolAssignment(supervisor=self.w.manager, school=self.w.other_school, start_date=self.w.today)
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_end_before_start_rejected(self):
        a = SchoolAssignment(supervisor=self.w.sup2, school=self.w.school, start_date=self.w.today,
                             end_date=self.w.today - timedelta(days=1))
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_active_supervisors(self):
        self.assertEqual(list(self.w.school.active_supervisors()), [self.w.sup])

    def test_school_card_access(self):
        url = reverse("org:school", args=[self.w.school.pk])
        self.client.force_login(self.w.sup)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.w.sup2)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.w.director)
        r = self.client.get(url)
        self.assertContains(r, self.w.school.name)
        self.assertContains(r, "—")  # القيم الفارغة تظهر «—»

    def test_school_list_filters(self):
        self.client.force_login(self.w.director)
        r = self.client.get(reverse("org:schools"), {"flag": "fi"})
        self.assertContains(r, self.w.fi_school.name)
        self.assertNotContains(r, self.w.school.name)
        self.client.force_login(self.w.sup)
        self.assertEqual(self.client.get(reverse("org:schools")).status_code, 403)

    def test_seed_command(self):
        from django.core.management import call_command
        from io import StringIO
        call_command("seed_demo", stdout=StringIO())
