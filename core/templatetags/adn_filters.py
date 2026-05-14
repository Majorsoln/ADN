from django import template

register = template.Library()


@register.filter
def tzs(value):
    """Format a number with thousand-separator commas, no decimals: 1000000 → 1,000,000"""
    try:
        return '{:,}'.format(int(round(float(value))))
    except (ValueError, TypeError):
        return value
