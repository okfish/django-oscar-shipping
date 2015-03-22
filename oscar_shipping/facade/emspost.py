import json
import itertools

from decimal import Decimal as D

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import ugettext_lazy as _
from django.utils.html import format_html_join

from emspost_api import emspost

from ..utils import del_key
from .base import AbstractShippingFacade
from ..exceptions import ( OriginCityNotFoundError, 
                           CityNotFoundError, 
                           ApiOfflineError, 
                           TooManyFoundError,
                           CalculationError )

API_CALC_OPTIONS = {}


API_OBJ_TYPES = {'cities'   : _("Russian Cities"),
                 'regions'  : _("Regions of Russia"),
                 'russia'   : _("All Russian Regions and Cities"),
                 'country'  : _("Foreign Countries"),
                 }


precision = D('0.0000')

class ShippingFacade(AbstractShippingFacade):
    name = 'emspost'
    
    def __init__(self, api_user=None, api_key=None):
        self.api = emspost.EmsAPI()

    def validate_code(self, code):
        """
            Returns False if code is not valid PEC city code,
            if not, returns code casted to int
        """
        qs = self.get_all_branches()
        if code in [i[0] for i in qs]:
            return code
        return None

    def get_by_code(self, code):
        """
            Returns city or branch title if code valid EMS city code,
            if not, returns None
        """
        qs = self.get_all_branches()
        for i in qs:
            if i[0] == code:
                return i[1]
        return None



    def get_charge(self, origin, dest, packs, options=None):
        res = errors = None
        if not options:
            options = API_CALC_OPTIONS
            
        options['from'] = origin
        options['to'] = dest
        options['weight'] = 0
        
        for pack in packs:
            options['weight'] += float(pack['weight'])
        
        res, errors = self.api.calculate(options)
        if 'rsp' in res.keys() :
            if not res['rsp']['stat'] == 'ok':
                raise CalculationError("%s(%s)" % (origin, dest), 
                                       res['rsp']['err'])        
            else:
                return res['rsp'], False
        else:
            errors = "No answer from API. Result was: %s" % res
        return res, errors        
        
        
    def get_charges(self, weight, packs, origin, dest):
        
        if not self.api.is_online():
            raise ApiOfflineError(_("Sorry. EMS API is offline right now"))
        
        # EMS origin and destination city or branch codes
        origin_code = dest_code = None  
        
        calc_result = err = errors = None
        city = ''
        try:
            origin_code, dest_code = self.get_city_codes(origin, dest)
        except:
            raise
       
        try:
            calc_result, err = self.get_charge(origin_code, dest_code, packs)
        except:
            raise
        if err:
            return err
        if calc_result:
            return calc_result
        else:
            raise CalculationError("Strange. No errors found but no"
                                   "response has received while "
                                   "calculating charge %s --> %s" % (origin_code, dest_code))

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
        
        if 'choices' in kwargs.keys():
            for r in kwargs['choices']:
                choices.append((r[0], r[1]))
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
            from .forms import EmsCalcForm
        except ImportError:
            return None
        return EmsCalcForm(*args, **kwargs)

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
        if hasattr(dest, 'city'):
            dest = dest.city
        weight = kwargs.get('weight', 1)
        packs = kwargs.get('packs', [])
        options = kwargs.get('options', False)

        if results and results['price']>0:
            #origin_code = results['senderCityId']
            #dest_code = results['receiverCityId']
            charge = D(results['price'])

            messages = u"""From %s to %s. Brutto: %s kg.
                        Packs: <ul>%s</ul>\n""" % (origin, 
                                                 dest, 
                                                 weight, 
                                                 format_html_join('\n', 
                                                 u"<li>{0} ({1}kg , {2}m<sup>3</sup>)</li>", 
                                                 ((p['container'].name, 
                                                   p['weight'], 
                                                   D(p['container'].volume).\
                                                    quantize(precision)) for p in packs)))
            if 'term' in results.keys():
                term = (results['term']['min'], results['term']['max'])
                messages += u"Delivery time: %s to %s days." % (term[0], term[1])
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
            n_qs.append({'id' : item[0],
                             'type' : item[2],
                             'text' : item[1],
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
        # Sort list of dicts by 'type' field
        key = lambda k: k['type']
        qs = sorted(qs, key=key)
        # Group it by 'type' field
        for k, g in itertools.groupby(qs, key):
            chld = list(g)
            # Remove unnec data
            for c in chld:
                del_key(c, 'type')
            res.append({'text' : "%s:" % unicode(API_OBJ_TYPES[k]), 
                        'children' : chld,
                    })
        return res