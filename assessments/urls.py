from django.urls import path

from . import views

app_name = "assessments"
urlpatterns = [
    path("<int:pk>/", views.form_detail, name="form"),
    path("reviews/", views.queue, name="queue"),
]
