from django.test import TestCase
from django.urls import reverse

from assessments.choices import FormStatus
from org.testing import World


class FormViewTests(TestCase):
    def setUp(self):
        self.w = World(items=2)
        self.form = self.w.executed_visit()
        self.url = reverse("assessments:form", args=[self.form.pk])
        self.r1, self.r2 = list(self.form.responses_ordered())

    def post(self, user, data):
        self.client.force_login(user)
        return self.client.post(self.url, data, follow=True)

    def test_close_with_missing_reason_shows_errors(self):
        r = self.post(self.w.sup, {"action": "close", f"ans_{self.r1.id}": "yes", f"ans_{self.r2.id}": "no",
                                   "summary": "س", "recommendations": "ت"})
        self.assertContains(r, "لا يمكن الإقفال")
        self.form.refresh_from_db()
        self.assertEqual(self.form.status, FormStatus.DRAFT)
        # حُفظت الإجابات المدخلة حتى مع فشل الإقفال
        self.r1.refresh_from_db()
        self.assertEqual(self.r1.answer, "yes")

    def test_close_success(self):
        r = self.post(self.w.sup, {"action": "close", f"ans_{self.r1.id}": "yes", f"ans_{self.r2.id}": "no",
                                   f"kind_{self.r2.id}": "not_present", f"reason_{self.r2.id}": "غائب",
                                   "summary": "س", "recommendations": "ت"})
        self.assertContains(r, "أُقفلت الاستمارة")
        self.form.refresh_from_db()
        self.assertEqual(self.form.status, FormStatus.CLOSED)

    def test_other_supervisor_cannot_view(self):
        self.client.force_login(self.w.sup2)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_manager_reviews_via_view(self):
        self.form.summary = self.form.recommendations = "x"
        for r in self.form.responses.all():
            r.answer = "yes"
            r.save()
        self.form.save()
        self.form.close(self.w.sup)
        self.post(self.w.manager, {"action": "review", "note": "جيد"})
        self.form.refresh_from_db()
        self.assertEqual(self.form.status, FormStatus.DEPT_REVIEWED)

    def test_supervisor_cannot_edit_closed_form(self):
        self.form.summary = self.form.recommendations = "x"
        for r in self.form.responses.all():
            r.answer = "yes"
            r.save()
        self.form.save()
        self.form.close(self.w.sup)
        self.client.force_login(self.w.sup)
        r = self.client.post(self.url, {"action": "save", f"ans_{self.r1.id}": "no"})
        self.assertEqual(r.status_code, 403)
