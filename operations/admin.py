from django.contrib import admin

from .models import ActivityType, ExecutionLog, NonExecutionReason, PlanItem, Visit, WeeklyPlan


class PlanItemInline(admin.TabularInline):
    model = PlanItem
    extra = 0


@admin.register(WeeklyPlan)
class WeeklyPlanAdmin(admin.ModelAdmin):
    list_display = ["supervisor", "week", "status", "submitted_at"]
    list_filter = ["status", "week"]
    inlines = [PlanItemInline]


@admin.register(ActivityType)
class ActivityTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active"]


@admin.register(NonExecutionReason)
class NonExecutionReasonAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "is_active"]
    list_filter = ["category"]


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ["school", "supervisor", "visit_type", "mode", "phase", "date"]
    list_filter = ["visit_type", "mode", "date"]


@admin.register(ExecutionLog)
class ExecutionLogAdmin(admin.ModelAdmin):
    list_display = ["plan_item", "executed", "reason", "recorded_at"]
