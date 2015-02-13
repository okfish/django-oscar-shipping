# template tags related to PECom shipping company API
from django import template

register = template.Library()

@register.inclusion_tag('oscar_shipping/partials/pecom_mini_calc.html')
def pecom_mini_calc(**kwargs):
    """
    Usage: {% pecom_mini_calc css=my_css_class %}
    """
    css_class = kwargs['css']
    return { 'css_class' : css_class }