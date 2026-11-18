from django.urls import path

from . import views

app_name = "org"
urlpatterns = [
    path("", views.school_list, name="schools"),
    path("<int:pk>/", views.school_card, name="school"),
]
