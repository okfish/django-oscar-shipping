# -*- coding: utf-8 -*-
from decimal import Decimal as D

from django.utils.translation import ugettext_lazy as _

OSCAR_SHIPPING_WEIGHT_PRECISION = D('0.000')

OSCAR_SHIPPING_VOLUME_PRECISION = D('0.000') 

# per product defaults
# 0.1m x 0.1m x 0.1m
OSCAR_SHIPPING_DEFAULT_BOX = {'width' : float('0.1'), 
                              'height' : float('0.1'), 
                              'lenght' : float('0.1') }

# 1 Kg 
OSCAR_SHIPPING_DEFAULT_WEIGHT = 1 

# basket volue * VOLUME_RATIO = estimated container(s) volume
# very simple method
OSCAR_SHIPPING_VOLUME_RATIO = D('1.3')

#default city of origin to calculate shipping cost via APIs
OSCAR_SHIPPING_DEFAULT_ORIGIN = u'Санкт-Петербург'

OSCAR_SHIPPING_API_ENABLED = ['pecom', 'emspost']