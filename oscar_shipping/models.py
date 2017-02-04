# -*- coding: utf-8 -*-
from decimal import Decimal as D

import importlib

from django.db import models
from django.conf import settings
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from django.core.validators import MinValueValidator
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import reverse_lazy

from oscar.apps.shipping.abstract_models import AbstractWeightBased
from oscar.core import prices, loading

from .packers import Packer
from .exceptions import (OriginCityNotFoundError,
                         CityNotFoundError,
                         ApiOfflineError,
                         TooManyFoundError,
                         CalculationError)

weight_precision = getattr(settings, 'OSCAR_SHIPPING_WEIGHT_PRECISION', D('0.000')) 
volume_precision = getattr(settings, 'OSCAR_SHIPPING_VOLUME_PRECISION', D('0.000'))

Scale = loading.get_class('shipping.scales', 'Scale')

DEFAULT_ORIGIN = getattr(settings, 'OSCAR_SHIPPING_DEFAULT_ORIGIN', 'Saint-Petersburg')

API_ENABLED = getattr(settings, 'OSCAR_SHIPPING_API_ENABLED', ['pecom', 'emspost'])

API_AVAILABLE = {'pecom': _('PEC API ver. 1.0'), 
                 'emspost': _('EMS Russian Post REST API'),
                 'dhl': _('DHL API (not ready yet)'),
                 'usps': _('USPS API (not ready yet)'),
                 }

CHANGE_DESTINATION = getattr(settings, 'OSCAR_SHIPPING_CHANGE_DESTINATION', True)


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
    return [(a, API_AVAILABLE[a]) for a in (API_ENABLED and api_modules_pool.keys())]


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
        Pre-populate destination field with the given address
        for charge calculating. Also, checks whether method allowed for this destination or not.
        :param addr: oscar.apps.address.models.UserAddress or subclassed instance (object must have 'line4' attr)
        :returns: list of available shipping methods for Repository class
        """
        methods = self.get_queryset()
        available_methods = []
        for m in methods:
            m.set_destination(addr)
            if m.destination_allowed is None or m.destination_allowed:
                available_methods.append(m)
        return available_methods


class ShippingCompany(AbstractWeightBased):
    """Shipping methods based on cargo companies APIs.
    """ 
    size_attributes = ('width', 'height', 'length')

    destination = None  # not stored field used for charge calculation

    errors = None
    messages = None

    ONLINE, OFFLINE, DISABLED = 'online', 'offline', 'disabled'
    API_STATUS_CHOICES = (
        (ONLINE, _('Online')),
        (OFFLINE, _('Offline')),
        (DISABLED, _('Disabled')),
    )

    PREPAID, POSTPAID = 'prepaid', 'postpaid'
    PAYMENT_CHOICES = (
        (PREPAID, _('Order includes shipping charges')),
        (POSTPAID, _('Shipping is paid by buyer'))
    )
    LIST_SEPARATOR = getattr(settings, 'OSCAR_SHIPPING_LIST_SEPARATOR', ';')
    SHOW_IF_NOT_FOUND = getattr(settings, 'OSCAR_SHIPPING_IF_NOT_FOUND', True)

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

    payment_type = models.CharField(verbose_name=_('payment type'),
                                    max_length=10,
                                    choices=PAYMENT_CHOICES,
                                    default=POSTPAID,
                                    blank=True)

    containers = models.ManyToManyField("ShippingContainer",
                                        blank=True,
                                        related_name='containers', 
                                        verbose_name=_('Containers or boxes'),
                                        help_text=_('Containers or boxes could be used for packing')
                                        )

    destination_whitelist = models.TextField(verbose_name=_('Destination codes whitelist'),
                                             help_text=_('Method will be available only for this destinations. '
                                                         'White list have a higher priority, if set, other lists will '
                                                         'be ignored. '
                                                         'Type of codes depends on shipping API type. '
                                                         'Use symbol "%s" to separate values.' % LIST_SEPARATOR),
                                             blank=True,
                                             )

    destination_blacklist = models.TextField(verbose_name=_('Destination codes blacklist'),
                                             help_text=_('Method will be not available for this destinations. '
                                                         'Type of codes depends on shipping API type. '
                                                         'Use symbol "%s" to separate values.' % LIST_SEPARATOR),
                                             blank=True,
                                             )

    objects = ShippingCompanyManager()
    available = AvailableCompanyManager()

    def __init__(self, *args, **kwargs):
        super(ShippingCompany, self).__init__(*args, **kwargs)
        self.messages = []
        self.errors = []
        if self.api_type:
            self.facade = api_modules_pool[self.api_type].ShippingFacade(self.api_user, self.api_key)

    @property
    def is_prepaid(self):
        return self.payment_type == self.PREPAID

    @property
    def destination_allowed(self):
        # there are three cases possible:
        # 1. no codes found for city of destination given
        # 2. found the only code
        # 3. found some codes (rare but possible)
        # the last case is most complicated as we need to catch three rabbits again:
        # 3.1 all of codes are black|white listed
        # 3.2 none are black|white listed
        # 3.3 some of codes are listed <--- this case can be controlled via settings or smth else
        # for the moment we just simply allow to use the method in this situation
        if not self.destination:
            return
        f = self.facade
        city = self.destination.line4
        if not city:
            return
        dest_codes, errors = f.get_cached_codes(f.clean_city_name(city))
        if not dest_codes:
            return self.SHOW_IF_NOT_FOUND
        flags = []
        if self.destination_whitelist:
            for code in dest_codes:
                flags.append(code in self.destination_whitelist.split(self.LIST_SEPARATOR))
            if all(flags):
                return True
            elif any(flags):
                return None
            else:
                return False
        flags = []
        if self.destination_blacklist:
            for code in dest_codes:
                flags.append(code in self.destination_blacklist.split(self.LIST_SEPARATOR))
            if all(flags):
                return False
            else:
                return True
        else:
            return True

    def calculate(self, basket, options=None):
        # TODO: move code to smth like ShippingCalculator class
        results = []
        charge = D('0.0')
        self.messages = []
        self.errors = []
        # Note, when weighing the basket, we don't check whether the item
        # requires shipping or not.  It is assumed that if something has a
        # weight, then it requires shipping.
        scale = Scale(attribute_code=self.weight_attribute,
                      default_weight=self.default_weight)
        packer = Packer(self.containers,
                        attribute_codes=self.size_attributes,
                        weight_code=self.weight_attribute, 
                        default_weight=self.default_weight)
        weight = scale.weigh_basket(basket).quantize(weight_precision)
        # Should be a list of dicts { 'weight': weight, 'container' : container }
        packs = packer.pack_basket(basket)  
        facade = self.facade
        if not self.destination: 
            self.errors.append(_("ERROR! There is no shipping address for charge calculation!\n"))
        else:
            self.messages.append(_(u"""Approximated shipping price
                                for {weight} kg from {origin} 
                                to {destination}\n""").format(weight=weight, 
                                                              origin=self.origin,
                                                              destination=self.destination.city))
            
            # Assuming cases like http protocol suggests:
            # e=200  - OK. Result contains charge value and extra info such as Branch code, etc
            # e=404  - Result is empty, no destination found via API, redirect 
            #          to address form or prompt to API city-codes selector
            # e=503  - API is offline. Skip this method.
            # e=300  - Too many choices found, Result contains list of charges-codes. 
            #          Prompt to found dest-codes selector  

            # an URL for AJAXed city-to-city charge lookup
            details_url = reverse_lazy('shipping:charge-details', kwargs={'slug': self.code})
            # an URL for AJAXed code by city lookup using Select2 widget
            lookup_url = reverse_lazy('shipping:city-lookup', kwargs={'slug': self.code})
            
            # if options set make a short call to API for final calculation  
            if options:
                errors = None
                try:
                    results, errors = facade.get_charge(options['senderCityId'], 
                                                        options['receiverCityId'],
                                                        packs)
                except CalculationError as e:
                    self.errors.append("Post-calculation error: %s" % e.errors)
                    self.messages.append(e.title)
                except:
                    raise
                if not errors:
                    (charge, msg,
                     err, self.extra_form) = facade.parse_results(results,
                                                                  options=options)
                    if msg:
                        self.messages.append(msg)
                    if err:
                        self.errors.append(err)
                else:
                    raise CalculationError("%s -> %s" % (options['senderCityId'], 
                                                         options['receiverCityId']), 
                                           errors)
            else:            
                try:          
                    results = facade.get_charges(weight, packs, self.origin, self.destination)
                except ApiOfflineError:
                    self.errors.append(_(u"""%s API is offline. Can't
                                         calculate anything. Sorry!""") % self.name)
                    self.messages.append(_(u"Please, choose another shipping method!"))
                except OriginCityNotFoundError as e: 
                    # Paranoid mode as ImproperlyConfigured should be raised by facade
                    self.errors.append(_(u"""City of origin '%s' not found
                                      in the shipping company 
                                      postcodes to calculate charge.""") % e.title)
                    self.messages.append(_(u"""It seems like we couldn't find code
                                        for the city of origin (%s).
                                        Please, select it manually, choose another 
                                        address or another shipping method.
                                    """) % e.title)
                except ImproperlyConfigured as e:  # upraised error handling
                    self.errors.append("ImproperlyConfigured error (%s)" % e.message)
                    self.messages.append("Please, select another shipping method or call site administrator!")
                except CityNotFoundError as e: 
                    self.errors.append(_(u"""Can't find destination city '{title}'
                                      to calculate charge. 
                                      Errors: {errors}""").format(title=e.title, errors=e.errors))
                    self.messages.append(_(u"""It seems like we can't find code
                                        for the city of destination (%s).
                                        Please, choose
                                        another address or another shipping method.
                                    """) % e.title)
                    if CHANGE_DESTINATION:
                        self.messages.append(_("Also, you can choose city of destination manually"))
                        self.extra_form = facade.get_extra_form(origin=self.origin,
                                                                lookup_url=lookup_url,
                                                                details_url=details_url)
                except TooManyFoundError as e:
                    self.errors.append(_(u"Found too many destinations for given city (%s)") % e.title)
                    if CHANGE_DESTINATION:
                        self.messages.append(_("Please refine your shipping address"))
                        self.extra_form = facade.get_extra_form(origin=self.origin,
                                                                choices=e.results,
                                                                details_url=details_url)
                except CalculationError as e:
                    self.errors.append(_(u"""Error occurred during charge
                                        calculation for given city (%s)""") % e.title)
                    self.messages.append(_(u"API error was: %s") % e.errors)
                    if CHANGE_DESTINATION:
                        self.extra_form = facade.get_extra_form(origin=self.origin,
                                                                details_url=details_url,
                                                                lookup_url=lookup_url)
                except:
                    raise
                else:
                    (charge, msg,
                     err, self.extra_form) = facade.parse_results(results,
                                                                  origin=self.origin,
                                                                  dest=self.destination,
                                                                  weight=weight,
                                                                  packs=packs)
                    if msg:
                        self.messages.append(msg)
                    if err:
                        self.errors.append(err)
        
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
    length = models.DecimalField(
        _("Length, m"), decimal_places=3, max_digits=12,
        validators=[MinValueValidator(D('0.00'))])
    max_load = models.DecimalField(
        _("Max loading, kg"), decimal_places=3, max_digits=12,
        validators=[MinValueValidator(D('0.00'))])
    
    def __str__(self):
        return self.name
    
    @property
    def volume(self):
        return D(self.height*self.width*self.length).quantize(volume_precision)
    
    class Meta:
        app_label = 'shipping'
        verbose_name = _("Shipping Container")
        verbose_name_plural = _("Shipping Containers")
