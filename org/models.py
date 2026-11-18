from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Department(models.Model):
    name = models.CharField("اسم القسم", max_length=120, unique=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="مدير القسم", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="managed_departments",
    )

    class Meta:
        verbose_name = "قسم"
        verbose_name_plural = "الأقسام"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Sector(models.Model):
    name = models.CharField("اسم القطاع", max_length=120, unique=True)
    code = models.CharField("الرمز", max_length=20, blank=True)
    notes = models.TextField("ملاحظات", blank=True)

    class Meta:
        verbose_name = "قطاع"
        verbose_name_plural = "القطاعات"
        ordering = ["name"]

    def __str__(self):
        return self.name


class School(models.Model):
    class Stage(models.TextChoices):
        KG = "kg", "رياض أطفال"
        PRIMARY = "primary", "ابتدائي"
        MIDDLE = "middle", "متوسط"
        SECONDARY = "secondary", "ثانوي"
        MULTI = "multi", "مجمّع"

    class Gender(models.TextChoices):
        BOYS = "boys", "بنين"
        GIRLS = "girls", "بنات"

    class Priority(models.IntegerChoices):
        NORMAL = 0, "اعتيادية"
        MEDIUM = 1, "متوسطة"
        HIGH = 2, "عالية"

    ministry_code = models.CharField("الرقم الوزاري", max_length=20, unique=True)
    name = models.CharField("اسم المدرسة", max_length=200)
    sector = models.ForeignKey(Sector, verbose_name="القطاع", on_delete=models.PROTECT, related_name="schools")
    stage = models.CharField("المرحلة", max_length=12, choices=Stage.choices)
    gender = models.CharField("بنين/بنات", max_length=6, choices=Gender.choices)
    principal_name = models.CharField("اسم القائد/ة", max_length=150, blank=True)
    principal_phone = models.CharField("جوال القائد/ة", max_length=20, blank=True)
    email = models.EmailField("بريد المدرسة", blank=True)
    phone = models.CharField("هاتف المدرسة", max_length=20, blank=True)
    address = models.CharField("العنوان / الحي", max_length=255, blank=True)
    location_url = models.URLField("رابط الموقع", blank=True)
    students_count = models.PositiveIntegerField("عدد الطلاب", null=True, blank=True)
    teachers_count = models.PositiveIntegerField("عدد المعلمين", null=True, blank=True)
    classes_count = models.PositiveIntegerField("عدد الفصول", null=True, blank=True)
    building_type = models.CharField("نوع المبنى", max_length=60, blank=True)
    is_first_improvement = models.BooleanField(
        "ضمن مدارس الأولى للتحسين", default=False,
        help_text="تظهر زيارة «الأولى للتحسين» فقط للمشرفين المسندة إليهم هذه المدرسة.",
    )
    priority = models.IntegerField("الأولوية", choices=Priority.choices, default=Priority.NORMAL)
    is_active = models.BooleanField("نشطة", default=True)
    notes = models.TextField("ملاحظات", blank=True)

    class Meta:
        verbose_name = "مدرسة"
        verbose_name_plural = "المدارس"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def active_assignments(self, on=None):
        return SchoolAssignment.objects.active(on).filter(school=self)

    def active_supervisors(self, on=None):
        from accounts.models import User
        return User.objects.filter(assignments__in=self.active_assignments(on)).distinct()


class AssignmentQuerySet(models.QuerySet):
    def active(self, on=None):
        on = on or timezone.localdate()
        return self.filter(start_date__lte=on).filter(Q(end_date__isnull=True) | Q(end_date__gte=on))


class SchoolAssignment(models.Model):
    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="المشرف", on_delete=models.CASCADE,
        related_name="assignments", limit_choices_to={"role": "supervisor"},
    )
    school = models.ForeignKey(School, verbose_name="المدرسة", on_delete=models.CASCADE, related_name="assignments")
    start_date = models.DateField("من تاريخ", default=timezone.localdate)
    end_date = models.DateField("إلى تاريخ", null=True, blank=True)
    notes = models.CharField("ملاحظات", max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AssignmentQuerySet.as_manager()

    class Meta:
        verbose_name = "إسناد مدرسة"
        verbose_name_plural = "إسناد المدارس"
        ordering = ["school__name"]

    def __str__(self):
        return f"{self.school} ← {self.supervisor}"

    def clean(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "تاريخ النهاية قبل تاريخ البداية."})
        if self.supervisor_id and getattr(self.supervisor, "role", None) != "supervisor":
            raise ValidationError({"supervisor": "يمكن الإسناد إلى المشرفين فقط."})
        if self.supervisor_id and self.school_id:
            overlap = SchoolAssignment.objects.filter(supervisor=self.supervisor, school=self.school).exclude(pk=self.pk)
            far = self.end_date or timezone.datetime.max.date()
            overlap = overlap.filter(start_date__lte=far).filter(Q(end_date__isnull=True) | Q(end_date__gte=self.start_date))
            if overlap.exists():
                raise ValidationError("يوجد إسناد متداخل لنفس المشرف والمدرسة.")

    @property
    def is_active(self):
        today = timezone.localdate()
        return self.start_date <= today and (self.end_date is None or self.end_date >= today)
