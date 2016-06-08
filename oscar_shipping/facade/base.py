import json

from decimal import Decimal as D

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import ugettext_lazy as _

from ..exceptions import (OriginCityNotFoundError,
                          CityNotFoundError,
                          ApiOfflineError,
                          TooManyFoundError,
                          CalculationError)

# local cache
origin_code = {}

# this is workaround for that cases when city name was filled in the shipping address form
# via third-party plugins and APIs, such as KLADR-API or Dadata
# and being prefixed with abbreviated settlement type
# that prefix usually separated by dot-space symbols and we should strip it out to make search over city codes
# So put this setting implicitly if you want enable this feature
CITY_PREFIX_SEPARATOR = getattr(settings, 'OSCAR_CITY_PREFIX_SEPARATOR', None)


class AbstractShippingFacade(object):
    
    # instantiated API class from corresponding package
    # should be initiated in __init__
    api = None 
    name = ''

    def get_cached_origin_code(self, origin):
        code = None
        cache_key = ':'.join([self.name, origin])
        try:
            code = origin_code[cache_key]
        except KeyError:
            pass
        if code:
            return code
        else:
            cities, error = self.api.findbytitle(origin)
            if not error and len(cities)>0:
                # WARNING! The only first found code used as origin
                origin_code[cache_key] = cities[0][0]
                return origin_code[cache_key]
            else:
                raise ImproperlyConfigured("It seems like origin point '%s'"
                                           "could'nt be validated for the method. Errors: %s" % (origin, error))

    def get_cached_codes(self, city):
        errors = False
        codes = []
        res = []
        cache_key = ':'.join([self.name, city])
        
        res = cache.get(cache_key) # should returns list of tuples like facade do but as json
        if not res:
            res, errors = self.api.findbytitle(city)
            if not errors:
                cache.set(cache_key, json.dumps(res))
            else:
                res = []
        else:
            res = json.loads(res)
        
        codes = [r[0] for r in res]
        if len(codes) > 1:
            # return full API answer to let user make a choice 
            errors = res
        
        return codes, errors

    def clean_city_name(self, city):
        if CITY_PREFIX_SEPARATOR:
            try:
                # take all after separator
                city = city.split(CITY_PREFIX_SEPARATOR, 1)[1]
            except KeyError:
                pass
        return city

    def get_city_codes(self, origin, dest):
        """
            Returns tuple of verified origin and destination codes
        """
        origin_code = None # city or branch code 
        dest_codes = []    # city or branch codes list
        calc_result = err = errors = None
        city = ''

        origin_code = self.validate_code(origin) or self.get_cached_origin_code(origin)
        if origin_code is None:
            raise OriginCityNotFoundError(origin)
        
        dest_codes.append(self.validate_code(dest))
        if not dest_codes[0]:
            city = dest.line4
            region = dest.state        
            if not city:
                raise CityNotFoundError('city_not_set')
            dest_codes, errors = self.get_cached_codes(self.clean_city_name(city))
        
        if not dest_codes:
            raise CityNotFoundError(city or dest, errors)
        if len(dest_codes) > 1: 
            raise TooManyFoundError(city or dest, errors)
        else:
            return origin_code, dest_codes[0]

    def get_all_branches(self):
        cache_key = "%s_branches" % self.name
        errors = False
        res = cache.get(cache_key)
        if not res:
            res, errors = self.api.get_branches()
            if not errors:
                cache.set(cache_key, json.dumps(res))
            else:
                res = []
        else:
            res = json.loads(res)
        
        return errors or res

    def get_by_code(self, code):
        """
            Returns False if code is not valid API city code,
            if not, returns code casted to int.

            Subclasses should implement it.
        """
        raise NotImplementedError
    
    def get_extra_form(self, *args, **kwargs):
        """
        Return additional form if ambiguous data posted 
        via shipping address form so calculate() method requires 
        user action.
        Subclasses should implement it.
        """
        pass

    def validate_code(self, code):
        """
            Returns False if code is not valid PEC city code,
            if not, returns code casted to int
            
            Subclasses should implement it.
        """
        raise NotImplementedError
    
    def get_charges(self, weight, packs, origin, dest):
        """
            Subclasses should implement it.
        """
        raise NotImplementedError
    
    def get_charge(self, origin, dest, packs, options=None):
        """
            Subclasses should implement it.
        """
        raise NotImplementedError
    
    def parse_results(self, results, **kwargs):
        """
            Parses results returned by get_charges() method.
            Get some additional kwargs for detailed info or extra form.
            Returns tuple (charge, messages, errors, extra_form)
            
            Subclasses should implement it.
        """
        raise NotImplementedError
    
    def get_queryset(self):
        """ Return normalized queryset-like list of dicts
            { 'id' : <city code>, 'branch' : <branch title>, 'text': <city title> }
            
            Subclasses should implement it.
        """
        raise NotImplementedError
    
    def format_objects(self, qs):
        """ Prepare data for select2 option list.
            Should return smth like grouped
                [{ 'text' : <branch_name>, 
                  'children' : { 'id' : <city_id>, 
                              'text' : <city_name> } 
                  ...
                },...]
             or
                [{ 'id' : <city_id>, 
                    'text' : <city_name> },...]
             for non-categorized lists.
                     
            Subclasses should implement it.
        """
        raise NotImplementedError
