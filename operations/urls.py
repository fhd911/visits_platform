from django.urls import path

from . import views

app_name = "operations"
urlpatterns = [
    path("", views.today, name="today"),
    path("plan/", views.my_plan, name="my_plan"),
    path("plan/<int:week_id>/", views.plan_view, name="plan"),
    path("schools/", views.my_schools, name="schools"),
    path("history/", views.history, name="history"),
    path("execution/", views.execution, name="execution"),
]
