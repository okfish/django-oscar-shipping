from decimal import Decimal as D

from django.core.exceptions import ImproperlyConfigured
from pecomsdk import pecom

origin_code = {}
cached_city_codes = {}



class ShippingFacade():
    kabinet = None
    def __init__(self, api_user=None, api_key=None):
        if api_user is not None and api_key is not None:
            self.kabinet = pecom.PecomCabinet(api_user, api_key)
        else:
             raise ImproperlyConfigured("No api credits specified for the shipping method 'pecom'")

    def get_cached_origin_code(self, origin):
        code = 0
        try:
            code = origin_code[origin]
        except KeyError:
            pass
        if code:
            return code
        else:
            cities, error = self.kabinet.findbytitle(origin)
            if not error:
                # WARNING! The only first found code used as origin
                origin_code[origin] = cities[0][0]
                return origin_code[origin]
            else:
                raise ImproperlyConfigured("It seems like origin point '%s' coudn't be validated for method 'pecom'" % origin)  

#     def get_cached_code(city):
#         error = False
#         if city in cached_city_codes.values()[1]:
#             return cached_city_codes[key]
#         elif city in cached_city_codes.values()[0]:
#             
#         else:
#             cities, error = self.kabinet.findbytitle(origin)
#             if not error:
#                 for city in cities:
#                     cached_city_codes[city[0]] = (city[1], city[2])
#             else 
                    
    
    def get_charge(self, weight, packs, origin, dest):
        #TODO: exceptions handling
        origin_code = self.get_cached_origin_code(origin)  
        return D(origin_code)