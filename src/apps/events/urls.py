from django.urls import path
from .views import (
    EventListView,
    EventDetailView,
    RegistrationCreateView,
    RegistrationCancelView,
)

urlpatterns = [
    path("", EventListView.as_view(), name="events"),
    path("<slug:slug>/", EventDetailView.as_view(), name="event_detail"),
    path("<slug:slug>/register/",
         RegistrationCreateView.as_view(), name="event_register"),
    path("<slug:slug>/cancel/", RegistrationCancelView.as_view(),
         name="event_cancel_registration"),
]
