import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.generic import TemplateView

from apps.events.models import Event
from apps.players.models import Player
from django.db.models import Count, Q

logger = logging.getLogger(__name__)


def health(request):
    return JsonResponse({'status': 'ok'})


def error_403(request, exception):
    return render(request, '403.html', status=403)


def error_404(request, exception):
    return render(request, '404.html', status=404)


def error_500(request):
    return render(request, '500.html', status=500)


class HomeView(TemplateView):
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['total_events'] = Event.objects.filter(
            status__in=[Event.Status.ACTIVE, Event.Status.COMPLETED]
        ).count()

        context['total_cities'] = Event.objects.filter(
            status__in=[Event.Status.ACTIVE, Event.Status.COMPLETED]
        ).values('city').distinct().count()

        context['total_players'] = Player.objects.count()

        context['upcoming_events'] = Event.objects.filter(
            status=Event.Status.ACTIVE,
            start_at__gte=timezone.now()
        ).select_related('city', 'game').order_by('start_at')[:10]

        return context


class AboutView(TemplateView):
    template_name = "pages/about.html"


class ContactView(TemplateView):
    template_name = "pages/contact.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form_id = settings.FORMSPREE_FORM_ID.strip()
        context['formspree_form_id'] = form_id
        context['formspree_action'] = (
            f'https://formspree.io/f/{form_id}' if form_id else ''
        )
        return context


class TermsView(TemplateView):
    template_name = "pages/terms.html"


class PrivacyView(TemplateView):
    template_name = "pages/privacy.html"
