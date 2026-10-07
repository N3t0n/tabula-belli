from django.shortcuts import render
from django.views.generic import DetailView
from django.utils import timezone
from django.db.models import Count, Q
from django.core.paginator import Paginator
from .models import Game


class GameDetailView(DetailView):
    model = Game
    template_name = 'games/game_detail.html'
    context_object_name = 'game'
    paginate_by = 12

    def get_template_names(self):
        """Return partial template for HTMX requests, full template otherwise."""
        if self.request.headers.get('HX-Request'):
            return ['games/_game_events_listing.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        requested_status = self.request.GET.get('status', '')
        status = (
            requested_status
            if requested_status in {'', 'upcoming', 'completed'}
            else ''
        )
        now = timezone.now()

        # Exclude canceled events
        events_qs = self.object.events.select_related(
            'organizer',
            'country',
            'region',
            'city'
        ).exclude(status='CANCELED').annotate(
            participants_count=Count(
                'registrations',
                filter=Q(registrations__status='CONFIRMED'),
                distinct=True
            )
        )

        # Apply status filters
        if status == 'upcoming':
            events_qs = events_qs.filter(status='ACTIVE', start_at__gte=now)
        elif status == 'completed':
            events_qs = events_qs.filter(status='COMPLETED', end_at__lt=now)
        # else: status == '' (All) - shows all non-canceled events

        events_qs = events_qs.order_by('start_at')

        paginator = Paginator(events_qs, self.paginate_by)
        page_obj = paginator.get_page(self.request.GET.get('page', 1))

        # Stats: only count non-canceled events
        context.update({
            'page_obj': page_obj,
            'status': status,
            'total_count': self.object.events.exclude(status='CANCELED').count(),
            'upcoming_count': self.object.events.filter(status='ACTIVE', start_at__gte=now).count(),
            'completed_count': self.object.events.filter(status='COMPLETED', end_at__lt=now).count(),
        })

        return context
