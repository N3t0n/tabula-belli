from django.views.generic import ListView, DetailView, View
from django.views.generic.edit import CreateView, UpdateView
from django.db.models import Q, Count, Subquery, OuterRef, Exists
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.urls import reverse
from urllib.parse import urlencode
from .models import Event, EventRegistration
from .forms import EventUserForm
from .mixins import VerifiedUserRequiredMixin, EventManagementRequiredMixin
from .policies import can_manage_event
from apps.games.models import Game
from cities_light.models import Country, Region, City


def _is_htmx(request):
    return bool(request.headers.get('HX-Request'))


def _registration_button_context(event, user_registration, *, oob_update=False):
    confirmed_count = getattr(event, 'participants_count', None)
    if confirmed_count is None:
        confirmed_count = EventRegistration.objects.filter(
            event=event,
            status=EventRegistration.Status.CONFIRMED,
        ).count()
        event.participants_count = confirmed_count

    registration_status = event.get_registration_status()
    return {
        'event': event,
        'user_registration': user_registration,
        'registration_status': registration_status,
        'registration_open': (
            registration_status == Event.RegistrationStatus.OPEN
        ),
        'is_full': registration_status == Event.RegistrationStatus.FULL,
        'confirmed_count': confirmed_count,
        'oob_update': oob_update,
    }


def _parse_query_id(value):
    if not isinstance(value, str) or not value or value != value.strip():
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class EventListView(ListView):
    """Event list with filters and pagination."""
    model = Event
    template_name = "events/events.html"
    context_object_name = "events"
    paginate_by = 12
    valid_statuses = {'', 'upcoming', 'completed'}
    valid_event_types = {'', *Event.EventType.values}
    valid_categories = {'', *Game.Category.values}
    valid_sorts = {
        'start_at', '-start_at',
        'game__name', '-game__name',
        'city__name', '-city__name',
        'participants_count', '-participants_count',
        'price', '-price',
    }

    def get_template_names(self):
        """Return partial for HTMX, full template otherwise."""
        if self.request.headers.get('HX-Request'):
            return ['events/_events_listing.html']
        return [self.template_name]

    def _get_filter_params(self):
        if hasattr(self, '_filter_params'):
            return self._filter_params

        raw_status = self.request.GET.get('status')
        status = 'upcoming' if raw_status is None else raw_status
        if status not in self.valid_statuses:
            status = ''

        event_type = self.request.GET.get('event_type', '')
        if event_type not in self.valid_event_types:
            event_type = ''

        category = self.request.GET.get('category', '')
        if category not in self.valid_categories:
            category = ''

        sort = self.request.GET.get('sort', 'start_at')
        if sort not in self.valid_sorts:
            sort = 'start_at'

        self._filter_params = {
            'status': status,
            'event_type': event_type,
            'category': category,
            'q': self.request.GET.get('q', '').strip(),
            'country': self.request.GET.get('country', ''),
            'region': _parse_query_id(self.request.GET.get('region', '')),
            'city': _parse_query_id(self.request.GET.get('city', '')),
            'game_id': _parse_query_id(self.request.GET.get('game_id', '')),
            'sort': sort,
        }
        return self._filter_params

    def _apply_filters(self, queryset, exclude_filters=None):
        exclude_filters = exclude_filters or set()
        filters = self._get_filter_params()

        if 'status' not in exclude_filters:
            status = filters['status']
            now = timezone.now()
            if status == 'upcoming':
                queryset = queryset.filter(status='ACTIVE', start_at__gte=now)
            elif status == 'completed':
                queryset = queryset.filter(
                    Q(status='COMPLETED') | Q(status='CANCELED'),
                    end_at__lt=now
                )

        if 'event_type' not in exclude_filters:
            event_type = filters['event_type']
            if event_type:
                queryset = queryset.filter(event_type=event_type)

        if 'category' not in exclude_filters:
            category = filters['category']
            if category:
                queryset = queryset.filter(game__category=category)

        if 'search' not in exclude_filters:
            q = filters['q']
            if q:
                queryset = queryset.filter(
                    Q(title__icontains=q) | Q(game__name__icontains=q)
                )

        if 'country' not in exclude_filters:
            country = filters['country']
            if country:
                queryset = queryset.filter(country__code2=country)

        if 'region' not in exclude_filters:
            region = filters['region']
            if region is not None:
                queryset = queryset.filter(region__geoname_id=region)

        if 'city' not in exclude_filters:
            city = filters['city']
            if city is not None:
                queryset = queryset.filter(city_id=city)

        if 'game' not in exclude_filters:
            game_id = filters['game_id']
            if game_id is not None:
                queryset = queryset.filter(game_id=game_id)

        return queryset

    def get_queryset(self):
        """Get filtered events with participant counts."""
        queryset = Event.objects.select_related(
            'game', 'country', 'region', 'city', 'organizer'
        ).annotate(
            participants_count=Count(
                'registrations',
                filter=Q(registrations__status=EventRegistration.Status.CONFIRMED),
                distinct=True
            )
        )

        # Añadir estado de inscripción del usuario autenticado
        if self.request.user.is_authenticated:
            user_reg_status = EventRegistration.objects.filter(
                event=OuterRef('pk'),
                player=self.request.user,
                status=EventRegistration.Status.CONFIRMED
            ).values('status')[:1]

            queryset = queryset.annotate(
                user_registration_status=Subquery(confirmed_registration.values('status')[:1])
            )

        queryset = self._apply_filters(queryset)

        return queryset.order_by(self._get_filter_params()['sort'])

    def _get_availability_sets(self):
        base_qs = Event.objects.exclude(status='CANCELED')
        base_qs = self._apply_filters(base_qs, exclude_filters={
            'country', 'region', 'city', 'game'
        })

        available_countries = set(
            base_qs.values_list('country__code2', flat=True).distinct())

        qs_regions = self._apply_filters(base_qs, exclude_filters={
            'region', 'city', 'game'
        })
        available_regions = set(qs_regions.values_list(
            'region__geoname_id', flat=True).distinct())

        qs_cities = self._apply_filters(base_qs, exclude_filters={
            'city', 'game'
        })
        available_cities = set(
            qs_cities.values_list('city_id', flat=True).distinct())

        qs_games = self._apply_filters(base_qs, exclude_filters={'game'})
        available_games = set(
            qs_games.values_list('game_id', flat=True).distinct())

        return {
            'available_countries': available_countries,
            'available_regions': available_regions,
            'available_cities': available_cities,
            'available_games': available_games,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = self._get_filter_params()
        context.update(self._get_availability_sets())
        context.update({
            'current_status': filters['status'],
            'current_event_type': filters['event_type'],
            'current_category': filters['category'],
            'current_country': filters['country'],
            'current_region': (
                str(filters['region']) if filters['region'] is not None else ''
            ),
            'current_city': (
                str(filters['city']) if filters['city'] is not None else ''
            ),
            'current_q': filters['q'],
            'current_sort': filters['sort'],
            'current_game_id': filters['game_id'],
        })

        category = context['current_category']
        context['games'] = (
            Game.objects.filter(category=category).order_by('name')
            if category else
            Game.objects.all().order_by('category', 'name')
        )

        context['countries'] = Country.objects.all().order_by('name')

        country = context['current_country']
        context['regions'] = (
            Region.objects.filter(country__code2=country).order_by('name')
            if country else []
        )

        region = filters['region']
        if region is not None:
            context['cities'] = City.objects.filter(
                region__geoname_id=region
            ).order_by('name')[:100]
        else:
            context['cities'] = []

        if self.request.headers.get('HX-Request'):
            clean_params = {}

            status = context['current_status']
            if status and status != 'upcoming':
                clean_params['status'] = status

            for key in [
                'event_type', 'category', 'game_id', 'country',
                'region', 'city', 'q'
            ]:
                value = filters[key]
                if value not in (None, ''):
                    clean_params[key] = value

            sort = context['current_sort']
            if sort and sort != 'start_at':
                clean_params['sort'] = sort

            page = self.request.GET.get('page', '1')
            if page != '1':
                clean_params['page'] = page

            context['_hx_replace_url'] = (
                f"{self.request.path}?{urlencode(clean_params)}"
                if clean_params else self.request.path
            )

        return context

    def render_to_response(self, context, **response_kwargs):
        """Add HX-Replace-Url header for HTMX."""
        response = super().render_to_response(context, **response_kwargs)
        if '_hx_replace_url' in context:
            response['HX-Replace-Url'] = context['_hx_replace_url']
        return response


class EventDetailView(DetailView):
    model = Event
    template_name = "events/event_detail.html"
    context_object_name = "event"

    def get_queryset(self):
        return Event.objects.select_related(
            'game', 'country', 'region', 'city', 'organizer'
        ).annotate(
            participants_count=Count(
                'registrations',
                filter=Q(registrations__status=EventRegistration.Status.CONFIRMED),
                distinct=True
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = context['event']
        now = timezone.now()

        is_past = event.end_at < now
        event_status_display = event.get_status_display()
        lat = getattr(event.city, 'latitude', None)
        lng = getattr(event.city, 'longitude', None)
        fallback_url = reverse('events')
        return_url = self.request.GET.get('return')
        if not url_has_allowed_host_and_scheme(
            return_url,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return_url = fallback_url

        user_registration = None
        can_manage = can_manage_event(self.request.user, event)
        confirmed_registrations = []

        if self.request.user.is_authenticated:
            user_registration = EventRegistration.objects.filter(
                event=event,
                player=self.request.user,
                status=EventRegistration.Status.CONFIRMED
            ).first()

            if can_manage:
                confirmed_registrations = event.registrations.filter(
                    status=EventRegistration.Status.CONFIRMED
                ).select_related('player').order_by('-created_at')

        registration_context = _registration_button_context(
            event, user_registration
        )
        context.update({
            'is_past': is_past,
            'event_status_display': event_status_display,
            'lat': lat,
            'lng': lng,
            'return_url': return_url,
            'can_manage_event': can_manage,
            'confirmed_registrations': confirmed_registrations,
            **registration_context,
        })

        return context


class RegistrationCreateView(VerifiedUserRequiredMixin, View):

    def post(self, request, slug):
        event = get_object_or_404(Event, slug=slug)

        try:
            registration = EventRegistration.register(
                event=event,
                player=request.user
            )

            if not _is_htmx(request):
                messages.success(request, 'Registration completed successfully.')
                return redirect('event_detail', slug=event.slug)

            return render(
                request,
                'events/partials/registration_button.html',
                _registration_button_context(
                    event, registration, oob_update=True
                ),
            )
        except ValidationError as e:
            error_msg = e.messages[0] if hasattr(e, 'messages') else str(e)
            if not _is_htmx(request):
                messages.error(request, error_msg)
                return redirect('event_detail', slug=event.slug)

            response = HttpResponse(
                f'<div class="text-red-600 text-sm mt-2">{error_msg}</div>',
                status=400
            )
            response['HX-Reswap'] = 'innerHTML'
            return response


class RegistrationCancelView(VerifiedUserRequiredMixin, View):

    def _my_events_response(self, request, *, error=None):
        context = _my_events_context(request, request.POST)
        context['registration_error'] = error
        context['registration_cancelled'] = error is None
        if not _is_htmx(request):
            notice = messages.error if error else messages.success
            notice(request, error or 'Registration cancelled successfully.')
            params = {key: request.POST[key] for key in
                      ('tab', 'q', 'status', 'org_page', 'part_page')
                      if key in request.POST}
            return redirect(f"{reverse('my_events:index')}?{urlencode(params)}")
        return render(request, 'events/partials/_my_events_content.html',
                      context, status=400 if error else 200)

    def post(self, request, slug):
        from apps.events.services import cancel_registration_for_actor

        event = get_object_or_404(Event, slug=slug)
        from_my_events = request.POST.get('source') == 'my-events'
        registration = EventRegistration.objects.filter(
            event=event, player=request.user,
            status=EventRegistration.Status.CONFIRMED,
        ).first()
        error = None
        if not registration:
            error = 'No active registration found'
        else:
            try:
                cancel_registration_for_actor(registration, request.user)
            except ValidationError as exc:
                error = '; '.join(exc.messages)

        if from_my_events:
            return self._my_events_response(request, error=error)
        if error:
            if not _is_htmx(request):
                messages.error(request, error)
                return redirect('event_detail', slug=event.slug)
            # Escape validation text rather than interpolating it into HTML.
            return HttpResponse(format_html(
                '<div class="text-red-600 text-sm mt-2">{}</div>', error,
            ), status=400)
        if not _is_htmx(request):
            messages.success(request, 'Registration cancelled successfully.')
            return redirect('event_detail', slug=event.slug)
        return render(
            request, 'events/partials/registration_button.html',
            _registration_button_context(event, None, oob_update=True),
        )


class MyEventsView(VerifiedUserRequiredMixin, ListView):
    template_name = 'events/my_events.html'

    def get_queryset(self):
        return Event.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_my_events_context(self.request, self.request.GET))
        return context


def _filter_my_events(qs, q, status):
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(game__name__icontains=q))
    if status in Event.Status.values:
        qs = qs.filter(status=status)
    return qs.order_by('-start_at')


def _my_events_context(request, params):
    active_tab = params.get('tab', 'organizing')
    if active_tab not in ['organizing', 'registered']:
        active_tab = 'organizing'

    q = params.get('q', '').strip()
    status = params.get('status', '').strip()

    organizing_qs = Event.objects.filter(
        organizer=request.user
    ).select_related(
        'game', 'city', 'country'
    ).annotate(
        participants_count=Count(
            'registrations',
            filter=Q(registrations__status=EventRegistration.Status.CONFIRMED),
            distinct=True
        )
    )

    # Membership is independent of the join used to count all participants.
    confirmed_registration = EventRegistration.objects.filter(
        event=OuterRef('pk'), player=request.user,
        status=EventRegistration.Status.CONFIRMED,
    )

    participating_qs = Event.objects.filter(Exists(confirmed_registration)).select_related(
        'game', 'city', 'country'
    ).annotate(
        participants_count=Count(
            'registrations',
            filter=Q(registrations__status=EventRegistration.Status.CONFIRMED),
            distinct=True
        ),
        user_registration_status=Subquery(confirmed_registration.values('status')[:1])
    ).distinct()

    organizing_qs = _filter_my_events(organizing_qs, q, status)
    participating_qs = _filter_my_events(participating_qs, q, status)

    org_paginator = Paginator(organizing_qs, 12)
    org_page_number = params.get('org_page', 1)
    organizing_page = org_paginator.get_page(org_page_number)

    part_paginator = Paginator(participating_qs, 12)
    part_page_number = params.get('part_page', 1)
    participating_page = part_paginator.get_page(part_page_number)

    return {
        'organizing_page': organizing_page,
        'participating_page': participating_page,
        'active_tab': active_tab,
        'q': q,
        'status': status,
    }


class EventCreateView(VerifiedUserRequiredMixin, CreateView):
    model = Event
    form_class = EventUserForm
    template_name = 'events/event_form.html'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.instance.organizer = self.request.user
        return form

    def get_initial(self):
        initial = super().get_initial()
        initial['contact_email'] = self.request.user.email
        return initial

    def form_valid(self, form):
        from apps.events.services import derive_initial_status

        form.instance.organizer = self.request.user
        form.instance.status = derive_initial_status(form.instance.end_at)
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('my_events:index')


class EventUpdateView(EventManagementRequiredMixin, VerifiedUserRequiredMixin, UpdateView):
    model = Event
    form_class = EventUserForm
    template_name = 'events/event_form.html'

    def dispatch(self, request, *args, **kwargs):
        event = self.get_object()

        if not event.is_editable():
            # Determine specific reason for better UX
            if event.status in [Event.Status.COMPLETED, Event.Status.CANCELED]:
                reason = f"it has status {event.get_status_display()}"
            else:
                reason = "it has already started"

            messages.error(
                request,
                f"Cannot edit this event because {reason}."
            )
            return redirect('my_events:index')

        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('my_events:index')


class EventCancelView(EventManagementRequiredMixin, VerifiedUserRequiredMixin, View):
    """
    Cancel an event (ACTIVE → CANCELED).
    Only the organizer or a superuser can cancel an event.
    """

    def post(self, request, slug):
        from apps.events.services import cancel_event

        event = self.get_object()

        try:
            cancel_event(event)
        except ValidationError as error:
            error_message = (
                error.messages[0]
                if hasattr(error, 'messages')
                else str(error)
            )
            if not _is_htmx(request):
                messages.error(request, error_message)
                return redirect('event_detail', slug=event.slug)

            return HttpResponse(
                f'<div class="text-red-600 text-sm">{error_message}</div>',
                status=400
            )

        if _is_htmx(request):
            return HttpResponse(
                status=204,
                headers={'HX-Redirect': reverse('my_events:index')}
            )

        messages.success(request, 'Event cancelled successfully.')
        return redirect('my_events:index')

    def get_object(self):
        return get_object_or_404(Event, slug=self.kwargs['slug'])


class OrganizerRemoveParticipantView(VerifiedUserRequiredMixin, View):
    """Remove participant from event."""

    def post(self, request, slug, reg_id):
        from apps.events.services import cancel_registration_for_actor

        event = get_object_or_404(Event, slug=slug)

        if not can_manage_event(request.user, event):
            if not _is_htmx(request):
                messages.error(
                    request, 'You do not have permission to manage this event.'
                )
                return redirect('event_detail', slug=event.slug)

            return HttpResponse(
                '<div class="text-destructive text-sm p-2 rounded bg-destructive/10">'
                'You do not have permission to manage this event.'
                '</div>',
                status=403
            )

        registration = get_object_or_404(
            EventRegistration,
            id=reg_id,
            event=event,
            status=EventRegistration.Status.CONFIRMED
        )

        try:
            cancel_registration_for_actor(registration, request.user)
        except ValidationError as e:
            if not _is_htmx(request):
                messages.error(request, str(e))
                return redirect('event_detail', slug=event.slug)

            return HttpResponse(
                f'<div class="text-destructive text-sm p-2 rounded bg-destructive/10">{str(e)}</div>',
                status=400
            )

        confirmed_count = EventRegistration.objects.filter(
            event=event,
            status=EventRegistration.Status.CONFIRMED
        ).count()

        if not _is_htmx(request):
            messages.success(request, 'Participant removed successfully.')
            return redirect('event_detail', slug=event.slug)

        return render(request, 'events/partials/participant_counter_update.html', {
            'event': event,
            'confirmed_count': confirmed_count,
            'reg_id': reg_id,
        }, status=200)
