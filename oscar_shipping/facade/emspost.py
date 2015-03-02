from decimal import Decimal as D

from ..exceptions import CityNotFoundError, ApiOfflineError

class ShippingFacade(object):
    def __init__(self, api_user=None, api_key=None):
        super(ShippingFacade, self).__init__()
    def get_charges(self, weight, volume, origin, dest):
        #TODO: get_charge method
        raise ApiOfflineError()