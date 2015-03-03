import json

from decimal import Decimal as D

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import ugettext_lazy as _
from django.utils.html import format_html_join

from pecomsdk import pecom

from ..exceptions import ( OriginCityNotFoundError, 
                           CityNotFoundError, 
                           ApiOfflineError, 
                           TooManyFoundError,
                           CalculationError )

PECOM_CALC_OPTIONS = {}

PECOM_TRANSPORT_TYPES = { 1 : _('Auto'),
                          2 : _('Avia'),
                          }

origin_code = {}

def to_int(val):
    # TODO: make it smarter
    try:
        casted = int(val)
    except (TypeError, ValueError, UnicodeEncodeError):
        return False
    return casted

class ShippingFacade():
    kabinet = None
    def __init__(self, api_user=None, api_key=None):
        if api_user is not None and api_key is not None:
            self.api_user, self.api_key = api_user, api_key
            self.kabinet = pecom.PecomCabinet(api_user, api_key)
        else:
             raise ImproperlyConfigured("No api credits specified for the shipping method 'pecom'")

    def get_cached_origin_code(self, origin):
        code = None
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

    def get_cached_codes(self, city):
        errors = False
        codes = []
        res = []
        
        res = cache.get(city) # should returns list of tuples like facade do but as json
        if not res:
            res, errors = self.kabinet.findbytitle(city)
            if not errors:
                cache.set(city, json.dumps(res))
            else:
                res = []
        else:
            res = json.loads(res)
        
        codes = [r[0] for r in res]
        if len(codes) > 1:
            # return full API answer to let user make a choice 
            errors = res
        
        return codes, errors

    def get_all_branches(self):
        cache_key = "pecom_branches_%s" % self.api_key
        errors = False
        res = []
        
        res = cache.get(cache_key)
        if not res:
            res, errors = self.kabinet.get_branches()
            if not errors:
                cache.set(cache_key, json.dumps(res))
            else:
                res = []
        else:
            res = json.loads(res)
        
        return errors or res 

    def get_charge(self, origin, dest, packs, options=None):
        if not options:
            options = PECOM_CALC_OPTIONS
            
        options['senderCityId'] = origin
        options['receiverCityId'] = dest
        options['Cargos'] = []
        for pack in packs:
            options['Cargos'].append({"length": float(pack['container'].lenght), 
                                      "width": float(pack['container'].width), 
                                      "height":float(pack['container'].height),
                                      "volume": float(pack['container'].volume), 
                                      "maxSize": 3.2,
                                      "isHP": False, 
                                      "sealingPositionsCount": 0, 
                                      "weight" : float(pack['weight']),
                                      "overSize": False
                                      })
        
        res, errors = self.kabinet.calculate(options)
        return res, errors
    
    def get_charges(self, weight, packs, origin, dest):
        origin_code = None # PEC city or branch code 
        dest_codes = []   # PEC city or branch codes list
        calc_result = err = errors = None
        city = ''
        #TODO: exceptions handling
        origin_code = to_int(origin) or self.get_cached_origin_code(origin)
        if origin_code is None:
            raise OriginCityNotFoundError(origin)
        
        
        dest_codes.append(to_int(dest))
        if not dest_codes[0]:
            city = dest.line4
            region = dest.state        
            if not city:
                raise CityNotFoundError('city_not_set')
            
            dest_codes, errors = self.get_cached_codes(city)
        
        if not dest_codes:
            raise CityNotFoundError(city or dest, errors)
        if len(dest_codes) > 1: 
            raise TooManyFoundError(city or dest, errors)
        else:
            calc_result, err = self.get_charge(origin_code, dest_codes[0], packs)
        
        if err:
            return err
        elif 'hasError' in calc_result.keys() :
            if calc_result['hasError']:
                raise CalculationError("%s(%s)" % (city, dest_codes[0]), calc_result['errorMessage'])
            elif len(calc_result['transfers']) > 0:
                calc_result['senderCityId'] = origin_code
                calc_result['receiverCityId'] = dest_codes[0]
                return calc_result
            else:   
                raise CalculationError(city, "Strange. No error found but no result present. DEBUG: %s" % calc_result)
        elif 'error' in calc_result.keys() :
            if calc_result['error']:
                raise CalculationError(city, "%s (%s)" % (calc_result['error']['title'],
                                                                               calc_result['error']['message']))
        else:
            raise CalculationError(city, """Strange. Seems like 
                                            no error field and no results 
                                            found via API. DEBUG: %s""" % calc_result)
    
    def get_extra_form(self, *args, **kwargs):
        """
        Return additional form if ambiguous data posted 
        via shipping address form so calculate() method requires 
        user action.
        If no initial data present return simple calc form with origin predefined
        If data given instantiate the choice form.   
        """
        origin_code = None
        
        if 'origin' in kwargs.keys():
            origin_code = self.get_cached_origin_code(kwargs.pop('origin'))
            if not 'initial' in kwargs.keys():
                kwargs['initial'] = { 'senderCityId': origin_code }
            else:
                kwargs['initial'].update({ 'senderCityId': origin_code })  
        # Return simple calculator form if no choices given: 
        # assuming entered city not found in branches 
        try:
            from .forms import PecomCalcForm
        except ImportError:
            return None
        return PecomCalcForm(*args, **kwargs)

    def get_transport_name(self, id):
        return PECOM_TRANSPORT_TYPES.get(id, '<unknown_transport_type>')
    
    def parse_results(self, results, **kwargs):
        """
            Parses results returned by get_charges() method.
            Get some additional kwargs for detailed info or extra form.
            Returns tuple (charge, messages, errors, extra_form)
        """
        origin_code = dest_code = None
        extra_form = None
        charge, messages, errors, extra_form = 0, '', '', None
        
        origin = kwargs.get('origin', '')
        dest = kwargs.get('dest', '')
        weight = kwargs.get('weight', 1)
        packs = kwargs.get('packs', [])
        options = kwargs.get('options', False)
        
        if options:
            if 'hasError' in results.keys() and not results['hasError']:
                for r in results['transfers']:
                    if r['transportingType'] == options['transportingType']:
                        messages = ''
                        return D(r['costTotal']), messages, errors, None
                        
            else:
                raise CalculationError("%s -> %s" % (options['senderCityId'], 
                                                     options['receiverCityId']), 
                                       results['errorMessage'])
        
        if results is not None and len(results['transfers'])>0:
            origin_code = results['senderCityId']
            dest_code = results['receiverCityId']
            
            if len(results['transfers'])>0:
                options = []
                for ch in results['transfers']:
                    opt = {}
                    if not ch['hasError']:
                        opt = {'id' : ch['transportingType'],
                           'name' : "%s" % unicode(self.get_transport_name(ch['transportingType'])), 
                           'cost': ch['costTotal'], 
                           #'errors' : '',
                           'services' : ch['services'], 
                           }
                        options.append(opt)
                    else:
                        errors += ch['errorMessage']
                    
                if len(options)>1:
                    extra_form = self.get_extra_form(options=options, 
                                                     full=True,
                                                     initial={ 'senderCityId': origin_code,
                                                               'receiverCityId': dest_code,
                                                              })
                else:
                    charge = D(results['transfers'][0]['costTotal'])
                    messages = u"""Ship by: %s from %s to %s. Brutto: %s kg. 
                                   Packs: <ul>%s</ul> """ % (
                                 self.get_transport_name(results['transfers'][0]['transportingType']),
                                 origin, 
                                 dest.city , 
                                 weight, 
                                 format_html_join('\n', 
                                 u"<li>{0} ({1}kg , {2}m<sup>3</sup>)</li>", 
                                 ((p['container'].name, 
                                   p['weight'], 
                                   D(p['container'].volume).\
                                    quantize(precision)) for p in packs)))

        else:
            errors += "Errors during facade.get_charges() method %s" % results
        
        
        return charge, message, errors, extra_form