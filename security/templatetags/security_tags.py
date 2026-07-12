from django import template

register = template.Library()

ROLE_BADGE_CLASSES = {
    'Administrador': 'bg-danger',
    'Vendedor': 'bg-success',
    'Analista de Compras': 'bg-warning text-dark',
}


@register.filter(name='role_badge_class')
def role_badge_class(role_name):
    """Clase Bootstrap del badge de color según el rol (gris si no está mapeado)."""
    return ROLE_BADGE_CLASSES.get(role_name, 'bg-secondary')


@register.filter(name='has_group')
def has_group(user, group_name):
    """
    Uso en template:
        {% load security_tags %}
        {% if user|has_group:'Vendedor' %} ... {% endif %}
    """
    if not user.is_authenticated:
        return False

    if user.is_superuser:      # el superusuario ve todo
        return True

    return user.groups.filter(name=group_name).exists()
