"""العمليات الميدانية: الخطة الأسبوعية، بنودها (زيارات وأنشطة)، التنفيذ اليومي، الزيارات."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from academic.models import AcademicYear, Holiday, StudyWeek, WORKDAYS
from assessments.choices import OPEN_FORM_STATUSES, Phase, VisitMode, VisitType


class ActivityType(models.Model):
    name = models.CharField("النشاط", max_length=120, unique=True)
    is_active = models.BooleanField("فعّال", default=True)

    class Meta:
        verbose_name = "نوع نشاط"
        verbose_name_plural = "أنواع الأنشطة الأخرى"
        ordering = ["name"]

    def __str__(self):
        return self.name


class NonExecutionReason(models.Model):
    class Category(models.TextChoices):
        SCHOOL = "school", "من جهة المدرسة"
        SUPERVISOR = "supervisor", "من جهة المشرف"
        ADMIN = "admin", "تكليف إداري"
        EXTERNAL = "external", "ظرف طارئ / خارجي"

    name = models.CharField("السبب", max_length=150, unique=True)
    category = models.CharField("الفئة", max_length=12, choices=Category.choices)
    is_active = models.BooleanField("فعّال", default=True)

    class Meta:
        verbose_name = "سبب عدم تنفيذ"
        verbose_name_plural = "أسباب عدم التنفيذ"
        ordering = ["category", "name"]

    def __str__(self):
        return self.name


class PlanBlocked(ValidationError):
    pass


def open_forms_for(supervisor, before=None):
    """استمارات زيارات منفذة لم تُقفل (تمنع إنشاء خطة جديدة)."""
    from assessments.models import FormInstance
    qs = FormInstance.objects.filter(visit__supervisor=supervisor, status__in=OPEN_FORM_STATUSES)
    if before:
        qs = qs.filter(visit__date__lt=before)
    return qs.select_related("visit__school")


class WeeklyPlan(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        SUBMITTED = "submitted", "معتمدة من المشرف"

    supervisor = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="المشرف", on_delete=models.CASCADE,
                                   related_name="plans")
    week = models.ForeignKey(StudyWeek, verbose_name="الأسبوع", on_delete=models.PROTECT, related_name="plans")
    status = models.CharField("الحالة", max_length=10, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField("ملاحظات", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "خطة أسبوعية"
        verbose_name_plural = "الخطط الأسبوعية"
        ordering = ["-week__start_date"]
        constraints = [models.UniqueConstraint(fields=["supervisor", "week"], name="uniq_plan_week")]

    def __str__(self):
        return f"خطة {self.supervisor} — {self.week}"

    @classmethod
    def blockers(cls, supervisor, week):
        return list(open_forms_for(supervisor, before=week.start_date))

    @classmethod
    def create_for(cls, supervisor, week):
        existing = cls.objects.filter(supervisor=supervisor, week=week).first()
        if existing:
            return existing
        if not supervisor.is_supervisor:
            raise ValidationError("الخطط الأسبوعية خاصة بالمشرفين.")
        blockers = cls.blockers(supervisor, week)
        if blockers:
            raise PlanBlocked(
                f"لا يمكن إنشاء خطة هذا الأسبوع: لديك {len(blockers)} استمارة غير مقفلة. أقفلها أولاً."
            )
        return cls.objects.create(supervisor=supervisor, week=week)

    @property
    def is_editable(self):
        return self.status == self.Status.DRAFT

    def submit(self):
        if not self.items.exists():
            raise ValidationError("أضف بنداً واحداً على الأقل قبل الاعتماد.")
        self.status = self.Status.SUBMITTED
        self.submitted_at = timezone.now()
        self.save(update_fields=["status", "submitted_at"])

    def stats(self):
        items = list(self.items.all())
        logged = [i for i in items if i.status != PlanItem.Status.PLANNED]
        executed = [i for i in logged if i.status == PlanItem.Status.EXECUTED]
        return {
            "total": len(items),
            "visits": sum(1 for i in items if i.kind == PlanItem.Kind.VISIT),
            "activities": sum(1 for i in items if i.kind == PlanItem.Kind.ACTIVITY),
            "logged": len(logged),
            "executed": len(executed),
            "rate": round(100 * len(executed) / len(logged)) if logged else None,
        }


def allowed_visit_types(supervisor, school, on=None):
    """أنواع الزيارات المتاحة للمشرف في مدرسة: الأولى للتحسين تظهر فقط للمسندة إليه مدرسة موسومة."""
    from org.models import SchoolAssignment
    if not SchoolAssignment.objects.active(on).filter(supervisor=supervisor, school=school).exists():
        return []
    types = [VisitType.SUPPORT, VisitType.TECHNICAL]
    if school.is_first_improvement:
        types.append(VisitType.FIRST_IMPROVEMENT)
    return types


def technical_phase_ready(school, phase, year):
    """مراحل الأداء الفني متتابعة: تخطيط ← مراجعة ← تقويم."""
    from assessments.models import FormInstance, previous_phase
    prev = previous_phase(phase)
    if prev is None:
        return True
    return FormInstance.objects.filter(
        cycle__school=school, cycle__year=year, cycle__visit_type=VisitType.TECHNICAL, cycle__phase=prev,
    ).exclude(status__in=OPEN_FORM_STATUSES).exists()


class PlanItem(models.Model):
    class Kind(models.TextChoices):
        VISIT = "visit", "زيارة"
        ACTIVITY = "activity", "نشاط آخر"

    class Status(models.TextChoices):
        PLANNED = "planned", "مخطط"
        EXECUTED = "executed", "منفّذ"
        NOT_EXECUTED = "not_executed", "لم يُنفّذ"

    plan = models.ForeignKey(WeeklyPlan, on_delete=models.CASCADE, related_name="items")
    date = models.DateField("اليوم")
    kind = models.CharField("النوع", max_length=10, choices=Kind.choices, default=Kind.VISIT)
    school = models.ForeignKey("org.School", verbose_name="المدرسة", null=True, blank=True, on_delete=models.PROTECT,
                               related_name="plan_items")
    visit_type = models.CharField("نوع الزيارة", max_length=20, choices=VisitType.choices, blank=True)
    mode = models.CharField("النمط", max_length=10, choices=VisitMode.choices, default=VisitMode.IN_PERSON)
    phase = models.CharField("المرحلة", max_length=12, choices=Phase.choices, blank=True)
    activity_type = models.ForeignKey(ActivityType, verbose_name="النشاط", null=True, blank=True,
                                      on_delete=models.PROTECT)
    notes = models.CharField("ملاحظات / الهدف", max_length=255, blank=True)
    status = models.CharField("الحالة", max_length=14, choices=Status.choices, default=Status.PLANNED)

    class Meta:
        verbose_name = "بند خطة"
        verbose_name_plural = "بنود الخطط"
        ordering = ["date", "id"]

    def __str__(self):
        if self.kind == self.Kind.VISIT:
            return f"{self.get_visit_type_display()} — {self.school}"
        return str(self.activity_type or "نشاط")

    @property
    def title(self):
        return str(self)

    def clean(self):
        errors = {}
        week = self.plan.week
        if not (week.start_date <= self.date <= week.end_date) or self.date.weekday() not in WORKDAYS:
            errors["date"] = "اختر يوم عمل ضمن أسبوع الخطة."
        elif Holiday.is_holiday(self.date):
            errors["date"] = "هذا اليوم إجازة في التقويم الدراسي."
        if self.kind == self.Kind.VISIT:
            if not self.school_id:
                errors["school"] = "اختر المدرسة."
            elif not self.visit_type:
                errors["visit_type"] = "اختر نوع الزيارة."
            elif self.visit_type not in allowed_visit_types(self.plan.supervisor, self.school, self.date):
                errors["visit_type"] = "نوع الزيارة غير متاح لك في هذه المدرسة (تحقق من الإسناد)."
            if self.visit_type == VisitType.TECHNICAL:
                if not self.phase:
                    errors["phase"] = "حدد مرحلة زيارة الأداء الفني."
                elif self.school_id and not technical_phase_ready(self.school, self.phase, week.year):
                    errors["phase"] = "لا يمكن البدء بهذه المرحلة قبل إقفال استمارة المرحلة السابقة لهذه المدرسة."
            elif self.phase:
                self.phase = ""
            self.activity_type = None
        else:
            if not self.activity_type_id:
                errors["activity_type"] = "اختر نوع النشاط."
            self.school = None
            self.visit_type = ""
            self.phase = ""
        if errors:
            raise ValidationError(errors)

    @transaction.atomic
    def log_execution(self, user, executed, reason=None, note=""):
        """تسجيل التنفيذ اليومي. الزيارة المنفذة تنشئ سجل زيارة واستمارتها."""
        if self.date > timezone.localdate():
            raise ValidationError("لا يمكن تسجيل تنفيذ بند في يوم لم يأتِ بعد.")
        if not executed and reason is None:
            raise ValidationError("اختر سبب عدم التنفيذ.")
        if hasattr(self, "visit") and not executed:
            form = getattr(self.visit, "form", None)
            if form and (not form.is_open or form.responses.exclude(answer="").exists()):
                raise ValidationError("لا يمكن تحويل زيارة بدأت استمارتها إلى «لم يُنفّذ».")
            self.visit.delete()
        log, _ = ExecutionLog.objects.update_or_create(
            plan_item=self,
            defaults={"executed": executed, "reason": None if executed else reason, "note": note,
                      "recorded_by": user},
        )
        self.status = self.Status.EXECUTED if executed else self.Status.NOT_EXECUTED
        self.save(update_fields=["status"])
        if executed and self.kind == self.Kind.VISIT and not hasattr(self, "visit"):
            from assessments.models import FormInstance
            visit = Visit.objects.create(
                plan_item=self, supervisor=self.plan.supervisor, school=self.school,
                visit_type=self.visit_type, mode=self.mode, phase=self.phase, date=self.date,
                year=self.plan.week.year,
            )
            FormInstance.create_for_visit(visit)
        return log


class ExecutionLog(models.Model):
    plan_item = models.OneToOneField(PlanItem, on_delete=models.CASCADE, related_name="execution")
    executed = models.BooleanField("نُفّذ")
    reason = models.ForeignKey(NonExecutionReason, verbose_name="سبب عدم التنفيذ", null=True, blank=True,
                               on_delete=models.PROTECT)
    note = models.CharField("ملاحظة", max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "سجل تنفيذ"
        verbose_name_plural = "سجلات التنفيذ"


class Visit(models.Model):
    plan_item = models.OneToOneField(PlanItem, null=True, blank=True, on_delete=models.SET_NULL, related_name="visit")
    supervisor = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="المشرف", on_delete=models.PROTECT,
                                   related_name="visits")
    school = models.ForeignKey("org.School", verbose_name="المدرسة", on_delete=models.PROTECT, related_name="visits")
    year = models.ForeignKey(AcademicYear, verbose_name="العام", on_delete=models.PROTECT, related_name="visits")
    visit_type = models.CharField("نوع الزيارة", max_length=20, choices=VisitType.choices)
    mode = models.CharField("النمط", max_length=10, choices=VisitMode.choices)
    phase = models.CharField("المرحلة", max_length=12, choices=Phase.choices, blank=True)
    date = models.DateField("التاريخ")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "زيارة"
        verbose_name_plural = "الزيارات"
        ordering = ["-date", "-id"]

    def __str__(self):
        label = self.get_visit_type_display()
        if self.phase:
            label += f" ({self.get_phase_display()})"
        return f"{label} — {self.school} — {self.date:%Y/%m/%d}"
