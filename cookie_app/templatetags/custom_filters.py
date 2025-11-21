from django import template

register = template.Library()

@register.filter
def avg(queryset, field_name):
    """Calculate average of a field in a queryset"""
    if not queryset:
        return 0
    
    total = 0
    count = 0
    
    for item in queryset:
        value = getattr(item, field_name, 0)
        if value is not None:
            total += float(value)
            count += 1
    
    return total / count if count > 0 else 0


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    return dictionary.get(key, 0)


@register.filter
def multiply(value, arg):
    """Multiply value by argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def divide(value, arg):
    """Divide value by argument"""
    try:
        return float(value) / float(arg) if float(arg) != 0 else 0
    except (ValueError, TypeError):
        return 0