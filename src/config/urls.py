"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from apps.pages.views import health

handler403 = 'apps.pages.views.error_403'
handler404 = 'apps.pages.views.error_404'
handler500 = 'apps.pages.views.error_500'

urlpatterns = [
    path('health/', health, name='health'),
    path('admin/', admin.site.urls),
    path('', include('apps.pages.urls')),
    path('events/', include('apps.events.urls')),
    path('my-events/', include('apps.events.my_events_urls')),
    path('games/', include('apps.games.urls')),
    path('accounts/', include('apps.accounts.allauth_urls')),
    path('accounts/', include('allauth.urls')),
    path('profile/', include('apps.accounts.urls')),
    path('locations/', include('apps.locations.urls')),
]
