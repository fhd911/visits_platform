from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from academic.models import Holiday
from assessments.choices import FormStatus, Phase, VisitType
from operations.models import PlanBlocked, PlanItem, Visit, WeeklyPlan, allowed_visit_types
from org.models import SchoolAssignment
from org.testing import World, fill


class PlanRulesTests(TestCase):
    def setUp(self):
        self.w = World(items=2)

    def test_open_form_blocks_next_week_plan(self):
        form = self.w.executed_visit()
        with self.assertRaises(PlanBlocked):
            WeeklyPlan.create_for(self.w.sup, self.w.week)
        fill(form, [("yes", "", ""), ("yes", "", "")])
        form.close(self.w.sup)
        self.assertIsNotNone(WeeklyPlan.create_for(self.w.sup, self.w.week))

    def test_other_supervisor_not_blocked(self):
        self.w.executed_visit()
        self.assertIsNotNone(WeeklyPlan.create_for(self.w.sup2, self.w.week))

    def test_first_improvement_only_for_assigned_flagged_school(self):
        w = self.w
        self.assertIn(VisitType.FIRST_IMPROVEMENT, allowed_visit_types(w.sup, w.fi_school))
        self.assertNotIn(VisitType.FIRST_IMPROVEMENT, allowed_visit_types(w.sup, w.school))
        self.assertEqual(allowed_visit_types(w.sup2, w.fi_school), [])  # غير مسندة إليه
        plan = w.plan()
        with self.assertRaises(ValidationError):
            w.add_visit(plan, school=w.school, visit_type=VisitType.FIRST_IMPROVEMENT)
        w.add_visit(plan, school=w.fi_school, visit_type=VisitType.FIRST_IMPROVEMENT)

    def test_cannot_plan_unassigned_school(self):
        with self.assertRaises(ValidationError):
            self.w.add_visit(self.w.plan(), school=self.w.other_school)

    def test_ended_assignment_removes_access(self):
        a = SchoolAssignment.objects.get(supervisor=self.w.sup, school=self.w.school)
        a.end_date = self.w.prev_week.start_date - timedelta(days=1)
        a.save()
        with self.assertRaises(ValidationError):
            self.w.add_visit(self.w.plan(), school=self.w.school)

    def test_technical_phases_are_sequential(self):
        w = self.w
        plan = w.plan()
        with self.assertRaises(ValidationError):
            w.add_visit(plan, visit_type=VisitType.TECHNICAL, phase=Phase.REVIEW)
        with self.assertRaises(ValidationError):
            w.add_visit(plan, visit_type=VisitType.TECHNICAL, phase="")
        item = w.add_visit(plan, visit_type=VisitType.TECHNICAL, phase=Phase.PLANNING)
        item.log_execution(w.sup, True)
        fill(item.visit.form, [("yes", "", "")] * 2)
        item.visit.form.close(w.sup)
        w.add_visit(plan, visit_type=VisitType.TECHNICAL, phase=Phase.REVIEW)

    def test_date_must_be_workday_in_week_and_not_holiday(self):
        w = self.w
        plan = w.plan()
        friday = plan.week.start_date + timedelta(days=5)
        with self.assertRaises(ValidationError):
            w.add_visit(plan, day=friday)
        with self.assertRaises(ValidationError):
            w.add_visit(plan, day=plan.week.start_date + timedelta(days=7))
        Holiday.objects.create(name="إجازة", start_date=plan.week.start_date, end_date=plan.week.start_date)
        with self.assertRaises(ValidationError):
            w.add_visit(plan)

    def test_activity_item(self):
        plan = self.w.plan()
        item = PlanItem(plan=plan, date=plan.week.start_date, kind="activity", activity_type=self.w.activity,
                        school=self.w.school, visit_type="support")
        item.full_clean()
        item.save()
        self.assertIsNone(item.school)
        item.log_execution(self.w.sup, True)
        self.assertFalse(Visit.objects.exists())

    def test_submit_requires_items(self):
        plan = self.w.plan()
        with self.assertRaises(ValidationError):
            plan.submit()
        self.w.add_visit(plan)
        plan.submit()
        self.assertEqual(plan.status, WeeklyPlan.Status.SUBMITTED)


class ExecutionTests(TestCase):
    def setUp(self):
        self.w = World(items=2)
        self.plan = self.w.plan()
        self.item = self.w.add_visit(self.plan)

    def test_executed_visit_creates_visit_and_form(self):
        self.item.log_execution(self.w.sup, True)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, PlanItem.Status.EXECUTED)
        self.assertEqual(self.item.visit.form.status, FormStatus.DRAFT)

    def test_not_executed_requires_reason(self):
        with self.assertRaises(ValidationError):
            self.item.log_execution(self.w.sup, False)
        self.item.log_execution(self.w.sup, False, self.w.reason, "أجلت")
        self.assertEqual(self.item.status, PlanItem.Status.NOT_EXECUTED)
        self.assertEqual(self.item.execution.reason, self.w.reason)
        self.assertFalse(Visit.objects.exists())

    def test_future_date_rejected(self):
        plan = WeeklyPlan.create_for(self.w.sup, self.w.next_week)
        item = self.w.add_visit(plan)
        with self.assertRaises(ValidationError):
            item.log_execution(self.w.sup, True)

    def test_correction_before_form_started(self):
        self.item.log_execution(self.w.sup, True)
        self.item.log_execution(self.w.sup, False, self.w.reason)
        self.assertFalse(Visit.objects.exists())

    def test_cannot_unexecute_after_form_started(self):
        self.item.log_execution(self.w.sup, True)
        r = self.item.visit.form.responses.first()
        r.answer = "yes"
        r.save()
        with self.assertRaises(ValidationError):
            self.item.log_execution(self.w.sup, False, self.w.reason)


class SupervisorPortalViewTests(TestCase):
    def setUp(self):
        self.w = World(items=2)
        self.client.force_login(self.w.sup)

    def test_pages_render(self):
        for name in ["operations:today", "operations:schools", "operations:history", "operations:execution"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        r = self.client.get(reverse("operations:my_plan"))
        self.assertRedirects(r, reverse("operations:plan", args=[self.w.week.pk]))

    def test_leadership_cannot_open_supervisor_portal(self):
        self.client.force_login(self.w.manager)
        self.assertEqual(self.client.get(reverse("operations:today")).status_code, 403)

    def test_create_plan_add_item_and_execute_via_views(self):
        url = reverse("operations:plan", args=[self.w.prev_week.pk])
        self.client.post(url, {"action": "create"})
        plan = WeeklyPlan.objects.get(supervisor=self.w.sup, week=self.w.prev_week)
        r = self.client.post(url, {"action": "add", "kind": "visit", "date": plan.week.start_date.isoformat(),
                                   "school": self.w.school.pk, "visit_type": "support", "mode": "remote"}, follow=True)
        self.assertContains(r, "أُضيف البند")
        item = plan.items.get()
        self.assertEqual(item.mode, "remote")
        r = self.client.post(reverse("operations:execution"), {"item": item.pk, f"i{item.pk}-executed": "1"})
        item.refresh_from_db()
        self.assertRedirects(r, reverse("assessments:form", args=[item.visit.form.pk]))
        # الاستمارة المفتوحة تمنع خطة الأسبوع الحالي
        r = self.client.get(reverse("operations:plan", args=[self.w.week.pk]))
        self.assertContains(r, "لا يمكن إنشاء خطة هذا الأسبوع")
        r = self.client.post(reverse("operations:plan", args=[self.w.week.pk]), {"action": "create"}, follow=True)
        self.assertFalse(WeeklyPlan.objects.filter(week=self.w.week).exists())

    def test_invalid_item_shows_error(self):
        url = reverse("operations:plan", args=[self.w.prev_week.pk])
        self.client.post(url, {"action": "create"})
        r = self.client.post(url, {"action": "add", "kind": "visit", "date": self.w.prev_week.start_date.isoformat(),
                                   "school": self.w.school.pk, "visit_type": "first_improvement", "mode": "in_person"})
        self.assertContains(r, "غير متاح لك")

    def test_execution_not_executed_without_reason(self):
        plan = self.w.plan()
        item = self.w.add_visit(plan)
        r = self.client.post(reverse("operations:execution"), {"item": item.pk, f"i{item.pk}-executed": "0"}, follow=True)
        self.assertContains(r, "اختر سبب عدم التنفيذ")
        item.refresh_from_db()
        self.assertEqual(item.status, PlanItem.Status.PLANNED)

    def test_cannot_log_other_supervisors_item(self):
        plan = self.w.plan(sup=self.w.sup2)
        item = self.w.add_visit(plan, school=self.w.other_school)
        r = self.client.post(reverse("operations:execution"), {"item": item.pk, f"i{item.pk}-executed": "1"})
        self.assertEqual(r.status_code, 404)
