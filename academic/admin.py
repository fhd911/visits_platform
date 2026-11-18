from django.contrib import admin, messages

from .models import AcademicYear, Holiday, StudyWeek, Term


class TermInline(admin.TabularInline):
    model = Term
    extra = 0


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ["name", "start_date", "end_date", "is_current"]
    inlines = [TermInline]


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ["name", "year", "start_date", "end_date"]
    actions = ["generate_weeks"]

    @admin.action(description="توليد الأسابيع الدراسية للفصول المحددة")
    def generate_weeks(self, request, queryset):
        n = sum(t.generate_weeks() for t in queryset)
        self.message_user(request, f"أُنشئ {n} أسبوعاً.", messages.SUCCESS)


@admin.register(StudyWeek)
class StudyWeekAdmin(admin.ModelAdmin):
    list_display = ["number", "year", "term", "start_date", "end_date", "is_teaching"]
    list_filter = ["year", "term", "is_teaching"]


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ["name", "start_date", "end_date"]
