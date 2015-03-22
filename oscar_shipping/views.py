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

class CityLookupView(CheckoutSessionMixin, View):
    """JSON lookup view for objects retrieved via REST API.
        Returns select2 compatible list.
    """
    def filter(self, data, predicate=lambda k, v: True):
        """
            Attemp to mimic django's queryset.filter() for simple lists
            proudly stolen from http://stackoverflow.com/a/1215039
            Usage:
                list(self.filter(test_data, lambda k, v: k == "key1" and v == "value1"))
        """
        for d in data:
             for k, v in d.items():
                   if predicate(k, v):
                        yield d
    
    def get_queryset(self):
        """ Return normalized queryset-like list of dicts
            { 'id' : <city code>, 'branch' : <branch title>, 'text': <city title> }
        """
        n_qs = []
        # Skip all not api-based methods
        if not hasattr(self.method, 'api_type'):
            return []
        
        self.facade = api_modules_pool[self.method.api_type].\
                    ShippingFacade(self.method.api_user, self.method.api_key)
        return self.facade.get_queryset()
         

    def format_object(self, qs):
        """ Prepare data for select2 option list.
            Should return smth like 
                [{ 'text' : <branch_name>, 
                  'children' : { 'id' : <city_id>, 
                              'text' : <city_name> } 
                  ...
                },...]
        """
        return self.facade.format_objects(qs)

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
        
class ShippingDetailsView(CheckoutSessionMixin, View):
    """
    Returns rendered detailed shipping charge form.
    Usage exapmle: 
    /shipping/details/pek/?from=[ORIGIN_CODE]&to=[DESTINATION_CODE]
    """
    # TODO: replace static field with get_template() 
    # method for easier customising
    template = "oscar_shipping/partials/details_form.html"
    def get_args(self):
        GET = self.request.GET
        return (GET.get('from', None),
                GET.get('to', None))

    def get(self, request, **kwargs):
        ctx = {}
        method = None
        origin = None
        dest = None
        self.request = request
        ctx['basket'] = request.basket
        method_code = kwargs['slug']
        for m in self.get_available_shipping_methods():
            if m.code == method_code:
                method = m
                ctx['method'] = method_code
        if not method:
            return HttpResponseBadRequest('Bad shipping method code!')
        facade = api_modules_pool[method.api_type].ShippingFacade(method.api_user, method.api_key)
        fromID, toID = self.get_args()
        if not fromID or not toID:
            return HttpResponseBadRequest('Required parameters not found in the query string!')
        origin = facade.get_by_code(fromID)
        dest = facade.get_by_code(toID)
       
        scale = Scale(attribute_code=method.weight_attribute,
                      default_weight=method.default_weight)
        packer = Packer(method.containers,
                        attribute_codes=method.size_attributes,
                        weight_code=method.weight_attribute,
                        default_weight=method.default_weight)
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
            charge, messages, errors, extra_form = facade.parse_results(charges, 
                                                                        origin=origin,
                                                                        dest=dest,
                                                                        weight=weight,
                                                                        packs=packs)
            if extra_form:
                ctx['form'] = extra_form 
            else:
                ctx['charge'] = charge
                ctx['messages'] = messages
                ctx['errors'] = errors
            return render(request, 
                              self.template, 
                              ctx, content_type="text/html" )