# -*- coding: utf-8 -*-
from decimal import Decimal as D

import json
import importlib

from django.db import models
from django.conf import settings
from django.contrib import messages
from django.utils.html import format_html_join
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from django.core.validators import MinValueValidator
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import reverse_lazy
from django.template.loader import render_to_string

from oscar.apps.shipping.abstract_models import AbstractWeightBased
from oscar.core import prices, loading

from .packers import Packer
from .exceptions import ( OriginCityNotFoundError, 
                          CityNotFoundError, 
                          ApiOfflineError, 
                          TooManyFoundError, 
                          CalculationError)

precision = D('.0000')

Scale = loading.get_class('shipping.scales', 'Scale')


DEFAULT_ORIGIN = u'Москва'

API_ENABLED = ['pecom', 'emspost']
API_AVAILABLE = {'pecom': _('PEC API ver. 1.0'), 
                 'emspost' :_('EMS Russian Post REST API'),
                 'dhl' : _('DHL API (not ready yet)'),
                 'usps' : _('USPS API (not ready yet)'),
                 }
ONLINE, OFFLINE, DISABLED = 'online','offline','disabled'
API_STATUS_CHOICES = (
    (ONLINE, _('Online')),
    (OFFLINE, _('Offline')),
    (DISABLED, _('Disabled')),
)

def get_api_modules():
    res = {}
    for name in API_AVAILABLE.keys():
        try:
            res[name] = importlib.import_module(".facade.%s" % name, __package__)
        except ImportError:
            pass 
    return res

api_modules_pool = get_api_modules()

def get_enabled_api():
    #mods = api_modules_pool
    return [(a, API_AVAILABLE[a]) for a in (API_ENABLED and api_modules_pool.keys()) ]

class ShippingCompanyManager(models.Manager):
    def get_queryset(self):
        """
        Just return original queryset
        """
        return super(ShippingCompanyManager, self).get_queryset()

class AvailableCompanyManager(ShippingCompanyManager):
    
    def get_queryset(self):
        """
        Filter out inactive methods (shipping companies with outdated contracts etc)
        """
        return super(AvailableCompanyManager, self).get_queryset().filter(is_active=True)
    
    def for_address(self, addr):
        """
        Prepopulate destination field with the given address 
        for charge calculating
        """
        methods = self.get_queryset()
        for m in methods:
            m.set_destination(addr)
        return methods

class ShippingCompany(AbstractWeightBased):
    """Shipping methods based on cargo companies APIs.
    """ 
    size_attributes = ('width' , 'height', 'lenght')

    destination = None # not stored field used for charge calculation
    
    errors = ''   # There is an issue with iterables and arrays as class properties and it scopes for class and instance
    messages = '' # so just a one string messages per calculate() method call 
                        
    api_user = models.CharField(_("API username"), max_length=64, blank=True)
    api_key = models.CharField(_("API key"), max_length=255, blank=True)
    api_type = models.CharField(verbose_name=_('API type'),
                                max_length=10, 
                                choices=get_enabled_api(), 
                                blank=True)
    origin = models.CharField(_("City of origin"), max_length=255, blank=True, default=DEFAULT_ORIGIN)
    is_active = models.BooleanField(_('active'), default=False,
                                        help_text=_('Use this method in checkout?'))
    status = models.CharField(verbose_name=_('status'),
                                max_length=10, 
                                choices=API_STATUS_CHOICES, 
                                blank=True)
    containers = models.ManyToManyField("ShippingContainer",
                                        blank=True,
                                        null=True,
                                        related_name='containers', 
                                        verbose_name=_('Containers or boxes'),
                                        help_text=_('Containers or boxes could be used for packing')
                                        )
    
    objects = ShippingCompanyManager()
    available = AvailableCompanyManager()

    def __init__(self, *args, **kwargs):
        super(ShippingCompany, self).__init__(*args, **kwargs)
        if self.api_type:
            self.facade = api_modules_pool[self.api_type].ShippingFacade(self.api_user, self.api_key)
        
    def calculate(self, basket, options=None):
        
        results = []
        charge = D('0.0')
        self.messages = ''
        self.errors = ''
        # Note, when weighing the basket, we don't check whether the item
        # requires shipping or not.  It is assumed that if something has a
        # weight, then it requires shipping.
        scale = Scale(attribute_code=self.weight_attribute,
                      default_weight=self.default_weight)
        packer = Packer(self.containers,
                        attribute_codes=self.size_attributes,
                        weight_code=self.weight_attribute, 
                        default_weight=self.default_weight)
        weight = scale.weigh_basket(basket)
        packs = packer.pack_basket(basket)  # Should be a list of dicts { 'weight': weight, 'container' : container }
        facade = self.facade
        if not self.destination: 
            self.errors+=_("ERROR! There is no shipping address for charge calculation!\n")
        else:
            self.messages+=_("""Approximated shipping price 
                                for %d kg from %s to %s\n""") % (weight, 
                                                              self.origin, 
                                                              self.destination.city)
            
            # Assuming cases like http protocol suggests:
            # e=200  - OK. Result contains charge value and extra info such as Branch code, etc
            # e=404  - Result is empty, no destination found via API, redirect to address form or prompt to API city-codes selector
            # e=503  - API is offline. Skip this method.
            # e=300  - Too many choices found, Result contains list of charges-codes. Prompt to found dest-codes selector  

            # an URL for AJAXed city-to-city charge lookup
            details_url = reverse_lazy('shipping:charge-details', kwargs={'slug': self.code})
            # an URL for AJAXed code by city lookup using Select2 widget
            lookup_url=reverse_lazy('shipping:city-lookup', kwargs={'slug': self.code})
            
            # if options set make a short call to API for final calculation  
            if options:
                errors = None
                try:
                    results, errors = facade.get_charge(options['senderCityId'], 
                                                options['receiverCityId'],
                                                packs)
                except CalculationError as e:
                    self.errors = "Post-calculation error: %s" % e.errors
                    self.messages = e.title
                except:
                    raise
                if not errors:
                    (charge, self.messages, 
                     self.errors, self.extra_form) = facade.parse_results(results, 
                                                                          options=options)
                else:
                    raise CalculationError("%s -> %s" % (options['senderCityId'], 
                                                         options['receiverCityId']), 
                                           errors)
            else:            
                try:          
                    results = facade.get_charges(weight, packs, self.origin, self.destination)
                except ApiOfflineError:
                    self.errors += _("%s API is offline. Cant calculate anything. Sorry!") % self.name
                    self.messages = _("Please, choose another shipping method!")
                except OriginCityNotFoundError as e: 
                    # Paranoid mode as ImproperlyConfigured should be raised by facade
                    self.errors += _("""City of origin '%s' not found 
                                      in the shipping company postcodes to calculate charge.""") % e.title
                    self.messages = _("""It seems like we couldnt find code for the city of origin (%s).
                                        Please, select it manually, choose another address or another shipping method.
                                    """) % e.title
                except ImproperlyConfigured as e: # upraised error handling
                    self.errors += "ImproperlyConfigured error (%s)" % e.message
                    self.messages = "Please, select another shipping method or call site administrator!"
                except CityNotFoundError as e: 
                    self.errors += _("""Cant find destination city '%s' 
                                      to calculate charge. Errors: %s""") % (e.title, e.errors)
                    self.messages = _("""It seems like we cant find code for the city of destination (%s).
                                        Please, select it manually, choose another address or another shipping method.
                                    """) % e.title
                    self.extra_form = facade.get_extra_form(origin=self.origin, 
                                                            lookup_url=lookup_url,
                                                            details_url=details_url)
                except TooManyFoundError as e:
                    self.errors += _("Found too many destinations for given city (%s)") % e.title
                    self.messages = _("Please refine your shipping address")
                    self.extra_form = facade.get_extra_form(origin=self.origin, 
                                                            choices=e.results,
                                                            details_url=details_url)
                except CalculationError as e:
                    self.errors += _("Error occured during charge calculation for given city (%s)") % e.title
                    self.messages = _("API error was: %s") % e.errors
                    self.extra_form = facade.get_extra_form(origin=self.origin,
                                                            details_url=details_url,
                                                            lookup_url=lookup_url)
                except:
                    raise
                else:
                  
                    (charge, self.messages, 
                     self.errors, self.extra_form) = facade.parse_results(results, 
                                                                            origin=self.origin,
                                                                            dest=self.destination,
                                                                            weight=weight,
                                                                            packs=packs)
        
        # Zero tax is assumed...
        return prices.Price(
            currency=basket.currency,
            excl_tax=charge,
            incl_tax=charge)
    
    def set_destination(self, addr):
        self.destination = addr
        
    class Meta(AbstractWeightBased.Meta):
        abstract = False
        app_label = 'shipping'
        verbose_name = _("API-based Shipping Method")
        verbose_name_plural = _("API-based Shipping Methods")



@python_2_unicode_compatible
class ShippingContainer(models.Model):
    name = models.CharField(_("Name"), max_length=128, unique=True)
    description = models.TextField(_("Description"), blank=True)
    image = models.ImageField(
        _("Image"), upload_to=settings.OSCAR_IMAGE_FOLDER, max_length=255, blank=True)
    height = models.DecimalField(
        _("Height, m"), decimal_places=3, max_digits=12,
        validators=[MinValueValidator(D('0.00'))])
    width = models.DecimalField(
        _("Width, m"), decimal_places=3, max_digits=12,
        validators=[MinValueValidator(D('0.00'))])
    lenght = models.DecimalField(
        _("Lenght, m"), decimal_places=3, max_digits=12,
        validators=[MinValueValidator(D('0.00'))])
    max_load = models.DecimalField(
        _("Max loading, kg"), decimal_places=3, max_digits=12,
        validators=[MinValueValidator(D('0.00'))])
    
    def __str__(self):
        return self.name
    
    @property
    def volume(self):
        return self.height*self.width*self.lenght
    
    class Meta():
        app_label = 'shipping'
        verbose_name = _("Shipping Container")
        verbose_name_plural = _("Shipping Containers")    