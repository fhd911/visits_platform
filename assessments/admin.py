from django.contrib import admin

from .models import FormInstance, FormItem, FormReview, FormTemplate, ItemResponse, VisitCycle


class FormItemInline(admin.TabularInline):
    model = FormItem
    extra = 1


@admin.register(FormTemplate)
class FormTemplateAdmin(admin.ModelAdmin):
    list_display = ["title", "visit_type", "phase", "is_active"]
    list_filter = ["visit_type", "is_active"]
    inlines = [FormItemInline]


class ResponseInline(admin.TabularInline):
    model = ItemResponse
    extra = 0
    readonly_fields = ["item", "answer", "reason_kind", "reason_text", "carried_from"]
    can_delete = False


class ReviewInline(admin.TabularInline):
    model = FormReview
    extra = 0
    readonly_fields = ["reviewer", "stage", "note", "returned", "created_at"]
    can_delete = False


@admin.register(FormInstance)
class FormInstanceAdmin(admin.ModelAdmin):
    list_display = ["visit", "status", "closed_at"]
    list_filter = ["status", "cycle__visit_type"]
    inlines = [ResponseInline, ReviewInline]
    readonly_fields = ["visit", "cycle", "closed_at", "closed_by"]


@admin.register(VisitCycle)
class VisitCycleAdmin(admin.ModelAdmin):
    list_display = ["school", "visit_type", "phase", "year", "status"]
    list_filter = ["visit_type", "status", "year"]
