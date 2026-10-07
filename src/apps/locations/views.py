import logging

from cities_light.models import City, Country, Region
from django.db import DatabaseError
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils.html import escape
from django.views.decorators.cache import cache_page

logger = logging.getLogger(__name__)

LOAD_ERROR_OPTION = '<option value="">Error loading locations</option>'


@cache_page(60 * 60 * 24)
def get_countries(request):
    try:
        countries = Country.objects.all().order_by('name')

        options = ['<option value="">Select country</option>']
        options.extend(
            f'<option value="{country.id}">{escape(country.name)}</option>'
            for country in countries
        )

        return HttpResponse(''.join(options))

    except DatabaseError:
        logger.exception('Country lookup failed')
        return HttpResponse(LOAD_ERROR_OPTION, status=503)


def get_regions(request):
    country_id = request.GET.get('country', '').strip()

    if not country_id:
        return HttpResponse('<option value="">Select country first</option>')

    try:
        country_pk = int(country_id)
    except (TypeError, ValueError):
        logger.warning('Rejected invalid country identifier')
        return HttpResponseBadRequest(LOAD_ERROR_OPTION)

    try:
        regions = Region.objects.filter(country_id=country_pk).order_by('name')

        options = ['<option value="">Select region</option>']

        for region in regions:
            options.append(
                f'<option value="{region.id}">{escape(region.name)}</option>')

        return HttpResponse(''.join(options))

    except DatabaseError:
        logger.exception('Region lookup failed')
        return HttpResponse(LOAD_ERROR_OPTION, status=503)


def get_cities(request):
    country_id = request.GET.get('country', '').strip()
    region_id = request.GET.get('region', '').strip()

    if not country_id:
        return HttpResponse('<option value="">Select country first</option>')

    try:
        filters = {'country_id': int(country_id)}
        if region_id:
            filters['region_id'] = int(region_id)
    except (TypeError, ValueError):
        logger.warning('Rejected invalid location identifier')
        return HttpResponseBadRequest(LOAD_ERROR_OPTION)

    try:
        cities = City.objects.filter(**filters).order_by('name')

        options = ['<option value="">Select city</option>']
        for city in cities:
            options.append(
                f'<option value="{city.id}">{escape(city.name)}</option>')

        return HttpResponse(''.join(options))

    except DatabaseError:
        logger.exception('City lookup failed')
        return HttpResponse(LOAD_ERROR_OPTION, status=503)
