from django.urls import path
from .views import (
    MyEventsView,
    EventCreateView,
    EventUpdateView,
    EventCancelView,
    OrganizerRemoveParticipantView,
)

app_name = 'my_events'

urlpatterns = [
    path('', MyEventsView.as_view(), name='index'),
    path('create/', EventCreateView.as_view(), name='create'),
    path('<slug:slug>/edit/', EventUpdateView.as_view(), name='edit'),
    path('<slug:slug>/cancel/', EventCancelView.as_view(), name='cancel'),
    path('<slug:slug>/participants/<int:reg_id>/remove/',
         OrganizerRemoveParticipantView.as_view(),
         name='remove_participant'),
]
