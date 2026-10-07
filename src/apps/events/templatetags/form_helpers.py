from django import template

register = template.Library()


@register.filter
def is_selected(field_value, option_value):
    """Return True when both values match after template coercion."""
    if field_value is None:
        return False
    return str(field_value) == str(option_value)
