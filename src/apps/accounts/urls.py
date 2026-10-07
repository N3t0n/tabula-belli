from django.urls import path
from .views import AccountDeleteView, ProfileView

app_name = 'accounts'

urlpatterns = [
    path('', ProfileView.as_view(), name='profile'),
    path('delete/', AccountDeleteView.as_view(), name='delete'),
]
