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



class ShippingCompany(AbstractWeightBased):
    """Shipping methods based on cargo companies APIs.
    """ 
    size_attributes = ('width' , 'height', 'lenght')
    default_volume = 1000
    
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

    def calculate(self, basket, dest):
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
        self.description = "%s Approximated shipping price for %s kg from %s to %s" % (self.description, weight, self.origin, dest.city)
        #
        charge = facade.get_charge(weight, packs, self.origin, dest)

        # Zero tax is assumed...
        return prices.Price(
            currency=basket.currency,
            excl_tax=charge,
            incl_tax=charge)
        
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