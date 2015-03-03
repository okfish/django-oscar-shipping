import json

from decimal import Decimal as D

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import ugettext_lazy as _

from emspost_api import emspost

from ..exceptions import ( OriginCityNotFoundError, 
                           CityNotFoundError, 
                           ApiOfflineError, 
                           TooManyFoundError,
                           CalculationError )

class ShippingFacade(object):
    api = None
    
    def __init__(self, api_user=None, api_key=None):
        self.api = emspost.EmsAPI()
    
    def get_charges(self, weight, volume, origin, dest):
        if not self.api.is_online():
            raise ApiOfflineError(_("Sorry. EMS API is offline right now"))
        raise CalculationError("Not implemented yet. Sorry")

    def get_extra_form(self, *args, **kwargs):
        """
        Return additional form if ambiguous data posted 
        via shipping address form so calculate() method requires 
        user action.
        If no initial data present return simple calc form with origin predefined
        If data given instantiate the choice form.   
        """

        # Return simple calculator form if no choices given: 
        # assuming entered city not found in branches 
        try:
            from .forms import EmsCalcForm
        except ImportError:
            return None
        return EmsCalcForm(*args, **kwargs)

