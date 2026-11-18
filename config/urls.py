from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import include, path

admin.site.site_header = "بوابة الزيارات — إدارة البيانات"
admin.site.site_title = "بوابة الزيارات"
admin.site.index_title = "البيانات الأساسية"


@login_required
def home(request):
    if request.user.is_supervisor:
        return redirect("operations:today")
    return redirect("command:dashboard")


urlpatterns = [
    path("", home, name="home"),
    path("accounts/", include("accounts.urls")),
    path("me/", include("operations.urls")),
    path("forms/", include("assessments.urls")),
    path("schools/", include("org.urls")),
    path("command/", include("command.urls")),
    path("admin/", admin.site.urls),
]
