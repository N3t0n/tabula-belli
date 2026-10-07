from django.urls import path
from .views import get_countries, get_regions, get_cities

app_name = 'locations'

urlpatterns = [
    path('countries/', get_countries, name='get_countries'),
    path('regions/', get_regions, name='get_regions'),
    path('cities/', get_cities, name='get_cities'),
]
