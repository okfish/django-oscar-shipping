# -*- coding: utf-8 -*-
from decimal import Decimal as D

import importlib

from django.db import models
from django.conf import settings
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from django.core.validators import MinValueValidator

from oscar.apps.shipping.abstract_models import AbstractWeightBased
from oscar.core import prices, loading

from .packers import Packer

Scale = loading.get_class('shipping.scales', 'Scale')


DEFAULT_ORIGIN = u'Москва'
DEFAULT_VOLUME = 1000 # for charge calculation if method requires but no attribute set for product
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
    default_volume = DEFAULT_VOLUME # basket (or item) volume for Packer if no dimentions defined for the product
    destination = None # not stored field used for charge calculation
                        
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
        
    def calculate(self, basket):
        
        charge = D('0.0')
        # Note, when weighing the basket, we don't check whether the item
        # requires shipping or not.  It is assumed that if something has a
        # weight, then it requires shipping.
        scale = Scale(attribute_code=self.weight_attribute,
                      default_weight=self.default_weight)
        packer = Packer(attribute_codes=self.size_attributes,
                        default_volume=self.default_volume)
        weight = scale.weigh_basket(basket)
        packs = packer.pack_basket(basket)  # Should be a list of pairs weight-container
        facade = api_modules_pool[self.api_type].ShippingFacade(self.api_user, self.api_key)
        if not self.destination: 
            self.description += "ERROR! There is no shipping address for charge calculation!"
        else:
            self.description = "%s Approximating shipping price for %d kg from %s to %s" % (self.description, weight, self.origin, self.destination.city)
        #
        charge = facade.get_charge(weight, packs, self.origin, self.destination)

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
        _("Height, cm"), decimal_places=3, max_digits=12,
        validators=[MinValueValidator(D('0.00'))])
    width = models.DecimalField(
        _("Width, cm"), decimal_places=3, max_digits=12,
        validators=[MinValueValidator(D('0.00'))])
    lenght = models.DecimalField(
        _("Lenght, cm"), decimal_places=3, max_digits=12,
        validators=[MinValueValidator(D('0.00'))])
    max_load = models.DecimalField(
        _("Max loading, kg"), decimal_places=3, max_digits=12,
        validators=[MinValueValidator(D('0.00'))])
    
    def __str__(self):
        return self.name

    class Meta():
        app_label = 'shipping'
        verbose_name = _("Shipping Container")
        verbose_name_plural = _("Shipping Containers")    