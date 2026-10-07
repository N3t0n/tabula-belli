from django import template
from django.http import QueryDict

register = template.Library()


@register.simple_tag(takes_context=True)
def pagination_url(context, page_number):
    request = context['request']
    params = request.GET.copy()
    params['page'] = page_number
    return f"{request.path}?{params.urlencode()}"
