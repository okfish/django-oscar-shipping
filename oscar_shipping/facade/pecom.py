import json
import itertools

from decimal import Decimal as D

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from django.utils.html import format_html_join
from django.conf import settings

from pecomsdk import pecom

from ..utils import del_key
from .base import AbstractShippingFacade
from ..exceptions import ( OriginCityNotFoundError, 
                           CityNotFoundError, 
                           ApiOfflineError, 
                           TooManyFoundError,
                           CalculationError )

PECOM_CALC_OPTIONS = {}

PECOM_TRANSPORT_TYPES = { 1 : _('Auto'),
                          2 : _('Avia'),
                          }

weight_precision = getattr(settings, 'OSCAR_SHIPPING_WEIGHT_PRECISION', D('0.000')) 

def to_int(val):
    # TODO: make it smarter
    try:
        casted = int(val)
    except (TypeError, ValueError, UnicodeEncodeError, AttributeError):
        return False
    return casted

class ShippingFacade(AbstractShippingFacade):
    name = 'pecom'
    messages_template = "oscar_shipping/partials/pecom_messages.html"
    
    def __init__(self, api_user=None, api_key=None):
        if api_user is not None and api_key is not None:
            self.api_user, self.api_key = api_user, api_key
            self.api = pecom.PecomCabinet(api_user, api_key)
        else:
             raise ImproperlyConfigured("No api credits specified for the shipping method 'pecom'")

    def validate_code(self, code):
        """
            Returns False if code is not valid PEC city code,
            if not, returns code casted to int
        """
        code_int = to_int(code)
        if not code_int:
            return False
        qs = self.get_all_branches()
        for item in qs:
            if code_int == to_int(item['bitrixId']):
                return code_int
            for c in item['cities']:
                city_id = to_int((c.get('bitrixId', None)))
                if city_id == code_int:
                    return code_int
        return None

    def get_by_code(self, code):
        """
            Returns city or branch title if code valid PEC city code,
            if not, returns None
        """
        code_int = to_int(code)
        if not code_int:
            return False
        qs = self.get_all_branches()
        for item in qs:
            if code_int == to_int(item['bitrixId']):
                return item['title']
            for c in item['cities']:
                city_id = to_int((c.get('bitrixId', None)))
                if city_id == code_int:
                    return item['title']
        return None
    
    def get_charge(self, origin, dest, packs, options=None):
        res = [] 
        errors = None
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
        
        res, errors = self.api.calculate(options)
        # FIXME: if no result has been returned there should be an issue like
        # 'NoneType' object does not support item assignment
        # errors: PecomCabinetException(error(6, "Couldn't resolve host 'kabinet.pecom.ru'"),)
        res['senderCityId'] = origin
        res['receiverCityId'] = dest
        return res, errors

    def get_charges(self, weight, packs, origin, dest):
        origin_code = dest_code = None # origin and destination city codes
        calc_result = err = None
        city = ''
        
        try:
            origin_code, dest_code = self.get_city_codes(origin, dest)
        except:
            raise
        calc_result, err = self.get_charge(origin_code, dest_code, packs)

        if err:
            return err
        elif 'hasError' in calc_result.keys() :
            if calc_result['hasError']:
                raise CalculationError("%s(%s)" % (city, dest_code), 
                                       calc_result['errorMessage'])
            elif len(calc_result['transfers']) > 0:

                return calc_result
            else:   
                raise CalculationError(city, "Strange. No error found"
                                             "but no result present. DEBUG: %s" % calc_result)
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
        choices = []

        if 'charges' in kwargs.keys():
            charges =  kwargs.pop('charges')
            options = []
            for ch in charges['transfers']:
                opt = {}
                if not ch['hasError']:
                    opt = {'id' : ch['transportingType'],
                       'name' : "%s" % unicode(facade.get_transport_name(ch['transportingType'])), 
                       'cost': ch['costTotal'], 
                       #'errors' : '',
                       'services' : ch['services'], 
                       }
                    options.append(opt)
            kwargs['options'] = options
    
        if 'choices' in kwargs.keys():
            for r in kwargs['choices']:
                choices.append((r[0], "%s (%s)" % (r[2], r[1]) ))
        kwargs['choices'] = choices
        
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
        charge, messages, errors, extra_form = 0, '', '', None
        
        origin = kwargs.get('origin', '')
        dest = kwargs.get('dest', '')
        if hasattr(dest, 'city'):
            dest = dest.city
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
                    tr_code = results['transfers'][0]['transportingType']
                    charge = D(results['transfers'][0]['costTotal'])
                    services = results['transfers'][0]['services']
                    msg_ctx = {'transport' : self.get_transport_name(tr_code),
                               'services': services,
                               'origin' : origin,
                               'destination' :  dest,
                               'total_weight' : D(weight).quantize(weight_precision),
                               'packs' : packs,
                               }
                    messages = render_to_string(self.messages_template, msg_ctx)
                    extra_form = self.get_extra_form(initial={ 'senderCityId': origin_code,
                                                               'receiverCityId': dest_code,
                                                               'transportingType': tr_code,
                                                              })

        else:
            errors += "Errors during facade.get_charges() method %s" % results
   
        return charge, messages, errors, extra_form

    def get_queryset(self):
        """ Return normalized queryset-like list of dicts
            { 'id' : <city code>, 'branch' : <branch title>, 'text': <city title> }
        """
        branch_title = ''
        branch_id = ''
        n_qs = []
        qs = self.get_all_branches()
        
        if not qs:
            return []
         
        for item in qs:
            branch_title = item['title']
            branch_id = item['bitrixId']
            n_qs.append({'id' : branch_id,
                             'branch' : branch_title,
                             'text' : branch_title,
                                      })
            for c in item['cities']:
                city_id = c.get('bitrixId', None)
                # Retreive only cities with ID
                if city_id:
                    n_qs.append({'id' : city_id,
                             'branch' : branch_title,
                             'text' : c['title'],
                                      })
        return n_qs
    
    def format_objects(self, qs):
        """ Prepare data for select2 grouped option list.
            Return smth like 
                [{ 'text' : <branch_name>, 
                  'children' : { 'id' : <city_id>, 
                              'text' : <city_name> } 
                  ...
                },...]
        """
        res = []
        chld = [] 
        # Sort list of dicts by 'branch' field
        key = lambda k: k['branch']
        qs = sorted(qs, key=key)
        # Group it by 'branch' field
        for k, g in itertools.groupby(qs, key):
            chld = list(g)
            # Remove unnec data
            for c in chld:
                del_key(c, 'branch')
            res.append({'text' : _("Branch: %s") % k, 
                        'children' : chld,
                    })
        return res