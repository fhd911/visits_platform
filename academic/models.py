from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

# أيام العمل: الأحد (6) إلى الخميس (3) وفق weekday() في بايثون
WORKDAYS = (6, 0, 1, 2, 3)
WEEKDAY_NAMES = {6: "الأحد", 0: "الاثنين", 1: "الثلاثاء", 2: "الأربعاء", 3: "الخميس", 4: "الجمعة", 5: "السبت"}


class AcademicYear(models.Model):
    name = models.CharField("العام الدراسي", max_length=30, unique=True, help_text="مثال: 1448هـ")
    start_date = models.DateField("البداية")
    end_date = models.DateField("النهاية")
    is_current = models.BooleanField("العام الحالي", default=False)

    class Meta:
        verbose_name = "عام دراسي"
        verbose_name_plural = "الأعوام الدراسية"
        ordering = ["-start_date"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.end_date and self.start_date and self.end_date <= self.start_date:
            raise ValidationError("نهاية العام يجب أن تكون بعد بدايته.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            AcademicYear.objects.exclude(pk=self.pk).update(is_current=False)

    @classmethod
    def current(cls):
        return cls.objects.filter(is_current=True).first()


class Term(models.Model):
    year = models.ForeignKey(AcademicYear, verbose_name="العام", on_delete=models.CASCADE, related_name="terms")
    name = models.CharField("الفصل الدراسي", max_length=50)
    start_date = models.DateField("البداية")
    end_date = models.DateField("النهاية")

    class Meta:
        verbose_name = "فصل دراسي"
        verbose_name_plural = "الفصول الدراسية"
        ordering = ["start_date"]

    def __str__(self):
        return f"{self.name} — {self.year}"

    def generate_weeks(self):
        """يولّد أسابيع دراسية (الأحد–الخميس) تغطي الفصل."""
        start = self.start_date - timedelta(days=(self.start_date.weekday() + 1) % 7)  # الأحد
        number = (StudyWeek.objects.filter(year=self.year).aggregate(m=models.Max("number"))["m"] or 0)
        created = 0
        while start <= self.end_date:
            if not StudyWeek.objects.filter(year=self.year, start_date=start).exists():
                number += 1
                StudyWeek.objects.create(
                    year=self.year, term=self, number=number,
                    start_date=start, end_date=start + timedelta(days=4),
                )
                created += 1
            start += timedelta(days=7)
        return created


class StudyWeek(models.Model):
    year = models.ForeignKey(AcademicYear, verbose_name="العام", on_delete=models.CASCADE, related_name="weeks")
    term = models.ForeignKey(Term, verbose_name="الفصل", null=True, blank=True, on_delete=models.SET_NULL, related_name="weeks")
    number = models.PositiveSmallIntegerField("رقم الأسبوع")
    start_date = models.DateField("بداية الأسبوع (الأحد)")
    end_date = models.DateField("نهاية الأسبوع (الخميس)")
    is_teaching = models.BooleanField("أسبوع دراسي", default=True, help_text="ألغِ التحديد لأسابيع الإجازة.")

    class Meta:
        verbose_name = "أسبوع دراسي"
        verbose_name_plural = "الأسابيع الدراسية"
        ordering = ["start_date"]
        constraints = [models.UniqueConstraint(fields=["year", "number"], name="uniq_week_number")]

    def __str__(self):
        return f"الأسبوع {self.number} ({self.start_date:%Y/%m/%d})"

    @classmethod
    def for_date(cls, d=None):
        d = d or timezone.localdate()
        return cls.objects.filter(start_date__lte=d, end_date__gte=d).first() or \
            cls.objects.filter(start_date__lte=d, start_date__gt=d - timedelta(days=7)).first()

    def next(self):
        return StudyWeek.objects.filter(start_date__gt=self.start_date).order_by("start_date").first()

    def previous(self):
        return StudyWeek.objects.filter(start_date__lt=self.start_date).order_by("-start_date").first()

    def workdays(self):
        holidays = set(Holiday.dates_between(self.start_date, self.end_date))
        days = []
        d = self.start_date
        while d <= self.end_date:
            if d.weekday() in WORKDAYS:
                days.append({"date": d, "name": WEEKDAY_NAMES[d.weekday()], "holiday": d in holidays})
            d += timedelta(days=1)
        return days


class Holiday(models.Model):
    name = models.CharField("المناسبة", max_length=120)
    start_date = models.DateField("من")
    end_date = models.DateField("إلى")

    class Meta:
        verbose_name = "إجازة"
        verbose_name_plural = "الإجازات"
        ordering = ["start_date"]

    def __str__(self):
        return self.name

    @classmethod
    def dates_between(cls, start, end):
        for h in cls.objects.filter(start_date__lte=end, end_date__gte=start):
            d = max(h.start_date, start)
            while d <= min(h.end_date, end):
                yield d
                d += timedelta(days=1)

    @classmethod
    def is_holiday(cls, d):
        return cls.objects.filter(start_date__lte=d, end_date__gte=d).exists()
