from django.urls import path

from . import views

app_name = "command"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("supervisors/", views.supervisors, name="supervisors"),
]
