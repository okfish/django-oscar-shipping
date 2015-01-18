from decimal import Decimal as D
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _

from oscar.apps.shipping import methods
from oscar.core import prices

class SelfPickup(methods.Free):
    """
    This shipping method specifies that goods can be picked up by customer.
    For free, of course
    """
    charge_incl_tax = None
    code = 'self-pickup'
    name = _('Self-service Pickup and shipping')
    description = _('Customers can pick up goods in the central store')
    def calculate(self, basket, shipping_address=None):
        # This method exists just to drop additional args
        return super(SelfPickup, self).calculate(basket)