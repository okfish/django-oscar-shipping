# -*- coding: UTF-8 -*-
import json
import itertools

from django.shortcuts import render
from django.contrib import messages
from django.core.cache import cache
from django.template.response import TemplateResponse
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.generic.base import View
from django.utils.translation import ugettext_lazy as _

from oscar.core.loading import get_class, get_classes, get_model

from .models import api_modules_pool
from .packers import Packer
from .exceptions import ( OriginCityNotFoundError, 
                          CityNotFoundError, 
                          ApiOfflineError, 
                          TooManyFoundError, 
                          CalculationError)

from .checkout.session import CheckoutSessionMixin
#CheckoutSessionMixin = get_class('checkout.session', 'CheckoutSessionMixin')
Repository = get_class('shipping.repository', 'Repository')
Scale = get_class('shipping.scales', 'Scale')

def del_key(dict, key):
    """Delete a pair key-value from dict given 
    """
    for k in list(dict.keys()):
        if k == key:
            del dict[k]


class PecomCityLookupView(CheckoutSessionMixin, View):
    """JSON lookup view for objects retrieved via REST API.
        Returns select2 compatible list.
    """
    def filter(self, data, predicate=lambda k, v: True):
        """
            Attemp to mimic django's queryset.filter() for simple lists
            proudly stolen from http://stackoverflow.com/a/1215039
            Usage:
                list(filter_data(test_data, lambda k, v: k == "key1" and v == "value1"))
        """
        for d in data:
             for k, v in d.items():
                   if predicate(k, v):
                        yield d
    
    def get_queryset(self):
        """Return normalized queryset-like list of dicts
        """
        n_qs = []
        branch_title = ''
        branch_id = ''
        qs = []
        
        # Skip all not api-based methods
        if not hasattr(self.method, 'api_type'):
            return []
        
        facade = api_modules_pool[self.method.api_type].\
                    ShippingFacade(self.method.api_user, self.method.api_key)
        qs = facade.get_all_branches()
        
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

    def format_object(self, qs):
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
        for k, g in itertools.groupby(qs, key ):
            chld = list(g)
            # Remove unnec data
            for c in chld:
                del_key(c, 'branch')
            res.append({'text' : "branch: %s" % k, 
                        'children' : chld,
                       })
        return res

    def initial_filter(self, qs, value):
        return self.filter(qs, lambda k, v: k == "id" and v in value.split(','))

    def lookup_filter(self, qs, term):
        return self.filter(qs, lambda k,v: k == "text" and term.lower() in v.lower() )

    def paginate(self, qs, page, page_limit):
        total = len(qs)

        start = (page - 1) * page_limit
        stop = start + page_limit

        qs = qs[start:stop]

        return qs, (page_limit * page < total)

    def get_args(self):
        GET = self.request.GET
        return (GET.get('initial', None),
                GET.get('q', None),
                int(GET.get('page', 1)),
                int(GET.get('page_limit', 20)))

    def get(self, request, **kwargs):
        self.request = request
        method_code = kwargs['slug']
        for m in self.get_available_shipping_methods():
            if m.code == method_code:
                self.method = m
        
        qs = self.get_queryset()

        initial, q, page, page_limit = self.get_args()

        if initial:
            qs = list(self.initial_filter(qs, initial))
            more = False
        else:
            if q:
                qs = list(self.lookup_filter(qs, q))
            qs, more = self.paginate(qs, page, page_limit)

        return HttpResponse(json.dumps({
            'results': self.format_object(qs),
            'more': more,
        }), content_type='application/json')
        
class PecomDetailsView(CheckoutSessionMixin, View):
    """
    Returns rendered detailed shipping charge form.
    Usage exapmle: 
    /shipping/details/pek/?from=[ORIGIN_CODE]&to=[DESTINATION_CODE]
    """
    template = "oscar_shipping/partials/pecom_details_form.html"
    def get_args(self):
        GET = self.request.GET
        return (GET.get('from', None),
                GET.get('to', None))

    def get(self, request, **kwargs):
        self.request = request
        method_code = kwargs['slug']
        for m in self.get_available_shipping_methods():
            if m.code == method_code:
                method = m
                
        facade = api_modules_pool[method.api_type].ShippingFacade(method.api_user, method.api_key)
        fromID, toID = self.get_args()
        if not fromID or not toID:
            return HttpResponseBadRequest()
        
        scale = Scale(attribute_code=method.weight_attribute,
                      default_weight=method.default_weight)
        packer = Packer(method.containers,
                        attribute_codes=method.size_attributes,
                        weight_code=method.weight_attribute)
        weight = scale.weigh_basket(request.basket)
        # Should be a list of dicts { 'weight': weight, 'container' : container }
        packs = packer.pack_basket(request.basket)  
        
        options = []
        try:
            charges = facade.get_charges(weight, packs, fromID, toID)
        except ApiOfflineError as e:
            messages.error(request, _('Oops. API is offline right now. Sorry.'))
            return render(request, 
                          self.template, 
                          { 'errors' : _('API is offline right now. Sorry. (%s)' % e.messages )} )
        except CalculationError as e:
            return render(request, 
                          self.template, 
                          { 'errors' : _('Calculator said: %s' % e.errors )} )
        else:
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
                else:
                    messages.error(request, _('Oops. API said: %s' % ch['errorMessage'] ))
                
            form = facade.get_extra_form(options=options)
            return render(request, 
                          self.template, 
                          { 'form' : form }, content_type="text/html" )
