from django.core.exceptions import ValidationError
from django.test import TestCase

from assessments.choices import Answer as A, FormStatus, Phase, ReasonKind as K, VisitType
from assessments.models import VisitCycle
from org.testing import World, fill

YES = (A.YES, "", "")
NO_ABSENT = (A.NO, K.NOT_PRESENT, "غير متواجد")
NO_IMPOSSIBLE = (A.NO, K.IMPOSSIBLE, "لا يمكن توفيره")
DEFERRED = (A.DEFERRED, "", "لم يتسع الوقت")


class FormEngineTests(TestCase):
    def setUp(self):
        self.w = World(items=4)

    def test_first_visit_gets_all_items(self):
        form = self.w.executed_visit()
        self.assertEqual(form.responses.count(), 4)
        self.assertEqual(form.status, FormStatus.DRAFT)

    def test_cannot_close_with_empty_fields(self):
        form = self.w.executed_visit()
        with self.assertRaises(ValidationError) as cm:
            form.close(self.w.sup)
        msgs = " ".join(cm.exception.messages)
        self.assertIn("اختر الإجابة", msgs)
        self.assertIn("ملخص الزيارة مطلوب", msgs)

    def test_no_requires_reason_kind_and_text(self):
        form = self.w.executed_visit()
        fill(form, [YES, YES, YES, (A.NO, "", "")])
        with self.assertRaises(ValidationError) as cm:
            form.close(self.w.sup)
        msgs = " ".join(cm.exception.messages)
        self.assertIn("نوع السبب", msgs)
        self.assertIn("اكتب سبب", msgs)

    def test_deferred_must_be_explained(self):
        form = self.w.executed_visit()
        fill(form, [YES, YES, YES, (A.DEFERRED, "", "")])
        with self.assertRaises(ValidationError):
            form.close(self.w.sup)

    def test_only_owner_can_close(self):
        form = self.w.executed_visit()
        fill(form, [YES] * 4)
        with self.assertRaises(ValidationError):
            form.close(self.w.sup2)

    def test_carry_over_rules(self):
        """«لا» غير قاطع و«مؤجَّل» يُرحَّلان؛ «نعم» و«لا» القاطع لا يُرحَّلان."""
        plan = self.w.plan()
        form1 = self.w.executed_visit(plan)
        fill(form1, [YES, NO_ABSENT, NO_IMPOSSIBLE, DEFERRED])
        form1.close(self.w.sup)
        self.assertEqual(form1.cycle.status, VisitCycle.Status.OPEN)

        item2 = self.w.add_visit(plan)
        item2.log_execution(self.w.sup, True)
        form2 = item2.visit.form
        self.assertEqual(form2.cycle, form1.cycle)
        carried = list(form2.responses_ordered())
        self.assertEqual([r.item.text for r in carried], ["بند 2", "بند 4"])
        self.assertTrue(all(r.carried_from is not None for r in carried))
        self.assertEqual(carried[0].carried_from.reason_kind, K.NOT_PRESENT)

        fill(form2, [YES, YES])
        form2.close(self.w.sup)
        form1.cycle.refresh_from_db()
        self.assertEqual(form1.cycle.status, VisitCycle.Status.COMPLETED)
        self.assertEqual(form1.cycle.progress()["pct"], 100)

    def test_completed_cycle_starts_new_one(self):
        form1 = self.w.executed_visit()
        fill(form1, [YES] * 4)
        form1.close(self.w.sup)
        form2 = self.w.executed_visit(self.w.plan())
        self.assertNotEqual(form2.cycle, form1.cycle)
        self.assertEqual(form2.responses.count(), 4)

    def test_cycles_are_per_visit_type(self):
        plan = self.w.plan()
        f1 = self.w.executed_visit(plan, school=self.w.fi_school)
        f2 = self.w.executed_visit(plan, school=self.w.fi_school, visit_type=VisitType.FIRST_IMPROVEMENT)
        self.assertNotEqual(f1.cycle, f2.cycle)
        self.assertEqual(f2.cycle.template, self.w.templates[(VisitType.FIRST_IMPROVEMENT, "")])

    def test_technical_phase_uses_phase_template(self):
        form = self.w.executed_visit(visit_type=VisitType.TECHNICAL, phase=Phase.PLANNING)
        self.assertEqual(form.cycle.template, self.w.templates[(VisitType.TECHNICAL, Phase.PLANNING)])


class ReviewFlowTests(TestCase):
    def setUp(self):
        self.w = World(items=2)
        self.form = self.w.executed_visit()
        fill(self.form, [YES, YES])
        self.form.close(self.w.sup)

    def test_full_chain_with_notes(self):
        w, f = self.w, self.form
        self.assertEqual(f.status, FormStatus.CLOSED)
        self.assertFalse(f.can_review(w.director))
        f.review(w.manager, "ملاحظة القسم")
        self.assertEqual(f.status, FormStatus.DEPT_REVIEWED)
        self.assertFalse(f.can_review(w.manager))
        f.review(w.director, "ملاحظة المدير")
        self.assertEqual(f.status, FormStatus.DIRECTOR_REVIEWED)
        f.review(w.assistant, "ملاحظة المساعد")
        self.assertEqual(f.status, FormStatus.APPROVED)
        self.assertEqual([r.stage_label for r in f.reviews.all()],
                         ["مدير القسم", "مدير الإدارة", "مساعد الشؤون التعليمية"])
        self.assertFalse(f.can_review(w.assistant))

    def test_note_required(self):
        with self.assertRaises(ValidationError):
            self.form.review(self.w.manager, "  ")

    def test_manager_of_other_department_cannot_review(self):
        from accounts.models import Role, User
        from org.models import Department
        other = User.objects.create_user("om@x.com", full_name="آخر", role=Role.DEPT_MANAGER)
        Department.objects.create(name="قسم آخر", manager=other)
        self.assertFalse(self.form.can_review(other))
        with self.assertRaises(ValidationError):
            self.form.review(other, "x")

    def test_return_to_supervisor_reopens_and_blocks(self):
        from operations.models import WeeklyPlan
        self.form.review(self.w.manager, "أكمل الشواهد", return_to_supervisor=True)
        self.assertEqual(self.form.status, FormStatus.RETURNED)
        self.assertTrue(self.form.is_open)
        self.assertTrue(WeeklyPlan.blockers(self.w.sup, self.w.week))
        self.form.close(self.w.sup)
        self.assertEqual(self.form.status, FormStatus.CLOSED)

    def test_review_queue(self):
        from assessments.services import review_queue
        self.assertEqual(list(review_queue(self.w.manager)), [self.form])
        self.assertEqual(review_queue(self.w.director).count(), 0)
        self.form.review(self.w.manager, "تم")
        self.assertEqual(list(review_queue(self.w.director)), [self.form])
