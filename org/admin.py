from django.contrib import admin

from .models import Department, School, SchoolAssignment, Sector


class AssignmentInline(admin.TabularInline):
    model = SchoolAssignment
    extra = 0
    autocomplete_fields = ["supervisor"]


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["name", "manager"]


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ["name", "code"]
    search_fields = ["name"]


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ["name", "ministry_code", "sector", "stage", "gender", "is_first_improvement", "priority", "is_active"]
    list_filter = ["sector", "stage", "gender", "is_first_improvement", "priority", "is_active"]
    search_fields = ["name", "ministry_code", "principal_name"]
    inlines = [AssignmentInline]
    fieldsets = (
        ("التعريف", {"fields": ("name", "ministry_code", "sector", "stage", "gender", "is_active")}),
        ("القيادة والتواصل", {"fields": ("principal_name", "principal_phone", "email", "phone", "address", "location_url")}),
        ("الأعداد والمبنى", {"fields": ("students_count", "teachers_count", "classes_count", "building_type")}),
        ("الأولويات", {"fields": ("is_first_improvement", "priority", "notes")}),
    )


@admin.register(SchoolAssignment)
class SchoolAssignmentAdmin(admin.ModelAdmin):
    list_display = ["school", "supervisor", "start_date", "end_date"]
    list_filter = ["school__sector", "supervisor"]
    search_fields = ["school__name", "supervisor__full_name"]
    autocomplete_fields = ["school", "supervisor"]
