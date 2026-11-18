from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["full_name"]
    list_display = ["full_name", "email", "role", "department", "sector", "max_schools", "is_active"]
    list_filter = ["role", "department", "sector", "is_active"]
    search_fields = ["full_name", "email"]
    fieldsets = (
        (None, {"fields": ("email", "full_name", "phone", "role")}),
        ("الارتباط التنظيمي", {"fields": ("department", "sector", "specialization", "max_schools")}),
        ("الصلاحيات", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
    )
    add_fieldsets = ((None, {"fields": ("email", "full_name", "role", "department", "sector")}),)
    filter_horizontal = ["groups"]
