from decimal import Decimal as D

class ShippingFacade(object):
    def __init__(self, api_user=None, api_key=None):
        super(ShippingFacade, self).__init__()
    def get_charge(self, weight, volume, origin, dest):
        #TODO: get_charge method
        return D('777.0')