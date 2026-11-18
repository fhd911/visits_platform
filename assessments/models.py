"""محرّك الاستمارات: القوالب، المسارات (تُستكمل عبر زيارات متتالية)، الإجابات، الترحيل، وسير المراجعة."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from accounts.models import Role

from .choices import (
    OPEN_FORM_STATUSES, PHASE_ORDER, Answer, FormStatus, Phase, ReasonKind, VisitType,
)


class FormTemplate(models.Model):
    visit_type = models.CharField("نوع الزيارة", max_length=20, choices=VisitType.choices)
    phase = models.CharField("المرحلة", max_length=12, choices=Phase.choices, blank=True,
                             help_text="لزيارة الأداء الفني فقط.")
    title = models.CharField("عنوان الاستمارة", max_length=200)
    description = models.TextField("وصف", blank=True)
    is_active = models.BooleanField("فعّالة", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "قالب استمارة"
        verbose_name_plural = "قوالب الاستمارات"
        ordering = ["visit_type", "phase"]

    def __str__(self):
        return self.title

    def clean(self):
        if self.visit_type == VisitType.TECHNICAL and not self.phase:
            raise ValidationError({"phase": "حدد مرحلة زيارة الأداء الفني."})
        if self.visit_type != VisitType.TECHNICAL and self.phase:
            raise ValidationError({"phase": "المراحل خاصة بزيارة الأداء الفني."})

    @classmethod
    def active_for(cls, visit_type, phase=""):
        return cls.objects.filter(visit_type=visit_type, phase=phase or "", is_active=True).order_by("-created_at").first()


class FormItem(models.Model):
    template = models.ForeignKey(FormTemplate, verbose_name="القالب", on_delete=models.CASCADE, related_name="items")
    section = models.CharField("المحور", max_length=120, blank=True)
    order = models.PositiveSmallIntegerField("الترتيب", default=0)
    text = models.CharField("نص البند", max_length=400)
    guidance = models.CharField("إرشاد", max_length=400, blank=True)
    is_active = models.BooleanField("فعّال", default=True)

    class Meta:
        verbose_name = "بند"
        verbose_name_plural = "البنود"
        ordering = ["template", "order", "id"]

    def __str__(self):
        return self.text


class VisitCycle(models.Model):
    """مسار استمارة لمدرسة: تُستكمل بنوده عبر زيارات متتالية حتى لا يبقى بند مُرحَّل."""

    class Status(models.TextChoices):
        OPEN = "open", "قيد الاستكمال"
        COMPLETED = "completed", "مكتمل"

    school = models.ForeignKey("org.School", verbose_name="المدرسة", on_delete=models.CASCADE, related_name="cycles")
    year = models.ForeignKey("academic.AcademicYear", verbose_name="العام", on_delete=models.PROTECT, related_name="cycles")
    visit_type = models.CharField("نوع الزيارة", max_length=20, choices=VisitType.choices)
    phase = models.CharField("المرحلة", max_length=12, choices=Phase.choices, blank=True)
    template = models.ForeignKey(FormTemplate, verbose_name="القالب", on_delete=models.PROTECT, related_name="cycles")
    status = models.CharField("الحالة", max_length=10, choices=Status.choices, default=Status.OPEN)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "مسار استمارة"
        verbose_name_plural = "مسارات الاستمارات"
        ordering = ["-started_at"]

    def __str__(self):
        label = self.get_visit_type_display()
        if self.phase:
            label += f" — {self.get_phase_display()}"
        return f"{self.school} · {label}"

    @classmethod
    def open_for(cls, school, visit_type, phase, year):
        """يعيد المسار المفتوح أو ينشئ مساراً جديداً بالقالب الفعّال."""
        cycle = cls.objects.filter(school=school, visit_type=visit_type, phase=phase or "", year=year,
                                   status=cls.Status.OPEN).first()
        if cycle:
            return cycle
        template = FormTemplate.active_for(visit_type, phase)
        if template is None:
            raise ValidationError("لا يوجد قالب استمارة فعّال لهذا النوع من الزيارات.")
        return cls.objects.create(school=school, visit_type=visit_type, phase=phase or "", year=year, template=template)

    def latest_closed_responses(self):
        """آخر إجابة لكل بند من الاستمارات المقفلة في هذا المسار."""
        latest = {}
        qs = ItemResponse.objects.filter(form__cycle=self).exclude(
            form__status__in=OPEN_FORM_STATUSES).select_related("form").order_by("form__closed_at", "id")
        for r in qs:
            latest[r.item_id] = r
        return latest

    def pending_items(self):
        """البنود التي لم تُحسم بعد (لم يُجب عنها، أو مُرحَّلة)."""
        latest = self.latest_closed_responses()
        items = self.template.items.filter(is_active=True)
        return [i for i in items if i.id not in latest or latest[i.id].is_carryable]

    def progress(self):
        total = self.template.items.filter(is_active=True).count()
        if not total:
            return None
        latest = self.latest_closed_responses()
        resolved = sum(1 for r in latest.values() if r.is_resolved and r.item.is_active)
        return {"total": total, "resolved": resolved, "pct": round(100 * resolved / total)}

    def refresh_status(self):
        if self.status == self.Status.OPEN and not self.pending_items():
            self.status = self.Status.COMPLETED
            self.completed_at = timezone.now()
            self.save(update_fields=["status", "completed_at"])


# انتقالات سير المراجعة: الحالة الحالية → (الدور المخوّل، الحالة التالية)
REVIEW_FLOW = {
    FormStatus.CLOSED: (Role.DEPT_MANAGER, FormStatus.DEPT_REVIEWED),
    FormStatus.DEPT_REVIEWED: (Role.DIRECTOR, FormStatus.DIRECTOR_REVIEWED),
    FormStatus.DIRECTOR_REVIEWED: (Role.EDU_ASSISTANT, FormStatus.APPROVED),
}


class FormInstance(models.Model):
    visit = models.OneToOneField("operations.Visit", verbose_name="الزيارة", on_delete=models.CASCADE, related_name="form")
    cycle = models.ForeignKey(VisitCycle, verbose_name="المسار", on_delete=models.PROTECT, related_name="forms")
    status = models.CharField("الحالة", max_length=20, choices=FormStatus.choices, default=FormStatus.DRAFT)
    summary = models.TextField("ملخص الزيارة", blank=True)
    recommendations = models.TextField("التوصيات", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField("تاريخ الإقفال", null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="closed_forms")

    class Meta:
        verbose_name = "استمارة زيارة"
        verbose_name_plural = "استمارات الزيارات"
        ordering = ["-created_at"]

    def __str__(self):
        return f"استمارة {self.visit}"

    @property
    def is_open(self):
        return self.status in OPEN_FORM_STATUSES

    @classmethod
    @transaction.atomic
    def create_for_visit(cls, visit):
        if hasattr(visit, "form"):
            return visit.form
        cycle = VisitCycle.open_for(visit.school, visit.visit_type, visit.phase, visit.year)
        form = cls.objects.create(visit=visit, cycle=cycle)
        latest = cycle.latest_closed_responses()
        for item in cycle.pending_items():
            ItemResponse.objects.create(form=form, item=item, carried_from=latest.get(item.id))
        return form

    def responses_ordered(self):
        return self.responses.select_related("item", "carried_from__form__visit").order_by("item__order", "item__id")

    def validation_errors(self):
        """يعيد قائمة الأخطاء التي تمنع الإقفال (لا حقل فارغ)."""
        errors = []
        for r in self.responses_ordered():
            errors.extend(f"البند «{r.item.text}»: {e}" for e in r.problems())
        if not self.summary.strip():
            errors.append("ملخص الزيارة مطلوب.")
        if not self.recommendations.strip():
            errors.append("التوصيات مطلوبة.")
        return errors

    @transaction.atomic
    def close(self, user):
        if not self.is_open:
            raise ValidationError("الاستمارة مقفلة مسبقاً.")
        if user != self.visit.supervisor:
            raise ValidationError("الإقفال من صلاحية المشرف صاحب الزيارة.")
        errors = self.validation_errors()
        if errors:
            raise ValidationError(errors)
        self.status = FormStatus.CLOSED
        self.closed_at = timezone.now()
        self.closed_by = user
        self.save(update_fields=["status", "closed_at", "closed_by"])
        self.cycle.refresh_status()

    def next_reviewer_role(self):
        step = REVIEW_FLOW.get(self.status)
        return step[0] if step else None

    def can_review(self, user):
        role = self.next_reviewer_role()
        if role is None:
            return False
        if user.is_superuser:
            return True
        if user.role != role:
            return False
        if role == Role.DEPT_MANAGER:
            dept = self.visit.supervisor.department
            return dept is not None and dept.manager_id == user.id
        return True

    @transaction.atomic
    def review(self, user, note, return_to_supervisor=False):
        if not self.can_review(user):
            raise ValidationError("لا تملك صلاحية المراجعة في هذه المرحلة.")
        note = (note or "").strip()
        if not note:
            raise ValidationError("اكتب ملاحظاتك على الاستمارة.")
        stage = self.status
        if return_to_supervisor:
            if stage != FormStatus.CLOSED:
                raise ValidationError("الإعادة للمشرف متاحة لمدير القسم فقط.")
            self.status = FormStatus.RETURNED
        else:
            self.status = REVIEW_FLOW[stage][1]
        self.save(update_fields=["status"])
        return FormReview.objects.create(form=self, reviewer=user, stage=stage, note=note,
                                         returned=return_to_supervisor)


class ItemResponse(models.Model):
    form = models.ForeignKey(FormInstance, on_delete=models.CASCADE, related_name="responses")
    item = models.ForeignKey(FormItem, on_delete=models.PROTECT, related_name="responses")
    answer = models.CharField("الإجابة", max_length=10, choices=Answer.choices, blank=True)
    reason_kind = models.CharField("نوع السبب", max_length=12, choices=ReasonKind.choices, blank=True)
    reason_text = models.TextField("السبب / التوضيح", blank=True)
    carried_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="carried_to", verbose_name="مُرحَّل من")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إجابة بند"
        verbose_name_plural = "إجابات البنود"
        constraints = [models.UniqueConstraint(fields=["form", "item"], name="uniq_response_item")]

    def __str__(self):
        return f"{self.item} — {self.get_answer_display() or '—'}"

    @property
    def is_resolved(self):
        return self.answer == Answer.YES or (self.answer == Answer.NO and self.reason_kind == ReasonKind.IMPOSSIBLE)

    @property
    def is_carryable(self):
        return not self.is_resolved

    def problems(self):
        p = []
        if not self.answer:
            p.append("اختر الإجابة أو علّمه «لم يُستكمل».")
        elif self.answer == Answer.NO:
            if not self.reason_kind:
                p.append("حدّد نوع السبب.")
            if not self.reason_text.strip():
                p.append("اكتب سبب الإجابة بـ«لا».")
        elif self.answer == Answer.DEFERRED and not self.reason_text.strip():
            p.append("وضّح سبب عدم الاستكمال.")
        return p


class FormReview(models.Model):
    form = models.ForeignKey(FormInstance, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="form_reviews")
    stage = models.CharField("المرحلة", max_length=20, choices=FormStatus.choices)
    note = models.TextField("الملاحظات")
    returned = models.BooleanField("أُعيدت للمشرف", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ملاحظة مراجعة"
        verbose_name_plural = "ملاحظات المراجعة"
        ordering = ["created_at"]

    @property
    def stage_label(self):
        return {
            FormStatus.CLOSED: "مدير القسم",
            FormStatus.DEPT_REVIEWED: "مدير الإدارة",
            FormStatus.DIRECTOR_REVIEWED: "مساعد الشؤون التعليمية",
        }.get(self.stage, "")


def previous_phase(phase):
    if phase not in PHASE_ORDER:
        return None
    i = PHASE_ORDER.index(phase)
    return PHASE_ORDER[i - 1] if i else None
