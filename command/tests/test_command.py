from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from command import metrics
from org.testing import World, fill


class MetricsTests(TestCase):
    def setUp(self):
        self.w = World(items=5)

    def test_ratio_returns_none_when_insufficient(self):
        self.assertIsNone(metrics.ratio(0, 0))
        self.assertIsNone(metrics.ratio(2, 2, min_den=3))
        self.assertEqual(metrics.ratio(1, 4), 25)

    def test_new_supervisor_has_dash_not_zero(self):
        ind = metrics.supervisor_indicators(self.w.sup, metrics.period_start(), timezone.localdate())
        self.assertIsNone(ind["execution"])
        self.assertIsNone(ind["results"])
        self.assertIsNone(ind["composite"])
        self.assertEqual(ind["coverage"], 0)

    def test_indicators_after_activity(self):
        w = self.w
        plan = w.plan()
        form = w.executed_visit(plan, school=w.fi_school)
        fill(form, [("yes", "", "")] * 3 + [("no", "not_present", "غائب"), ("no", "impossible", "مستحيل")])
        form.close(w.sup)
        w.add_visit(plan).log_execution(w.sup, False, w.reason)
        w.add_visit(plan).log_execution(w.sup, True)  # تبقى استمارة مفتوحة
        plan.submit()
        ind = metrics.supervisor_indicators(w.sup, metrics.period_start(), timezone.localdate())
        self.assertEqual(ind["coverage"], 100)
        self.assertEqual(ind["execution"], 67)
        self.assertEqual(ind["priority_coverage"], 100)
        self.assertEqual(ind["results"], 80)
        self.assertEqual(ind["open_forms"], 1)
        self.assertEqual(ind["followup"], 80)
        self.assertIsNotNone(ind["composite"])

    def test_ranking_not_by_visit_count(self):
        """مشرف بزيارات أكثر لكن بتغطية وإقفال أضعف لا يتصدر تلقائياً."""
        w = self.w
        plan2 = w.plan(sup=w.sup2)
        for _ in range(3):
            w.add_visit(plan2, school=w.other_school).log_execution(w.sup2, True)
        plan = w.plan()
        for school in (w.school, w.fi_school):
            f = w.executed_visit(plan, school=school)
            fill(f, [("yes", "", "")] * 5)
            f.close(w.sup)
        rows, _ = metrics.supervisors_table(w.director)
        self.assertEqual(rows[0]["supervisor"], w.sup)
        self.assertGreater(rows[1]["visits"], rows[0]["visits"])

    def test_dept_manager_scope(self):
        rows, _ = metrics.supervisors_table(self.w.manager)
        self.assertEqual([r["supervisor"] for r in rows], [self.w.sup])

    def test_dashboard_views(self):
        self.client.force_login(self.w.director)
        r = self.client.get(reverse("command:dashboard"))
        self.assertContains(r, "مركز القيادة")
        self.assertContains(r, "—")
        self.assertEqual(self.client.get(reverse("command:supervisors")).status_code, 200)
        self.assertEqual(self.client.get(reverse("assessments:queue")).status_code, 200)
        self.client.force_login(self.w.sup)
        self.assertEqual(self.client.get(reverse("command:dashboard")).status_code, 403)
