from decimal import Decimal as D

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _

from oscar.core import loading

Scale = loading.get_class('shipping.scales', 'Scale')

weight_precision = getattr(settings, 'OSCAR_SHIPPING_WEIGHT_PRECISION', D('0.000')) 
volume_precision = getattr(settings, 'OSCAR_SHIPPING_VOLUME_PRECISION', D('0.000')) 
# per product defaults
# 0.1m x 0.1m x 0.1m
DEFAULT_BOX = getattr(settings, 'OSCAR_SHIPPING_DEFAULT_BOX', {'width': float('0.1'),
                                                               'height': float('0.1'),
                                                               'lenght': float('0.1')})

# 1 Kg 
DEFAULT_WEIGHT = getattr(settings, 'OSCAR_SHIPPING_DEFAULT_WEIGHT', 1)

# basket volue * VOLUME_RATIO = estimated container(s) volume
# very simple method
VOLUME_RATIO = getattr(settings, 'OSCAR_SHIPPING_VOLUME_RATIO', D('1.3'))
                    

class Box(object):
    
    height = 0
    width = 0
    lenght = 0

    def __init__(self, h, w, l):
        self.height, self.width, self.lenght = h, w, l
    
    @property    
    def volume(self):
        return D(self.height*self.width*self.lenght).quantize(volume_precision)


class Container(Box):
    name = ''

    def __init__(self, h, w, l, name):
        self.name = name
        super(Container, self).__init__(h, w, l)


class ProductBox(Box):
    """
    'Packs' given product to the virtual box and scale it.
    Takes size and weight from product attributes (if present)
    """    
    weight = 0
    
    def __init__(self, 
                 product, 
                 size_codes=('width', 'height', 'length'),
                 weight_code='weight',
                 default_weight=DEFAULT_WEIGHT):
        self.attributes = size_codes
        attr_vals = {}
        scale = Scale(attribute_code=weight_code,
                      default_weight=default_weight)
        try:
            for attr in self.attributes:
                attr_vals[attr] = product.attribute_values.get(
                                                attribute__code=attr).value
        except ObjectDoesNotExist:
            attr_vals = DEFAULT_BOX
        self.weight = scale.weigh_product(product)
        for attr in attr_vals.keys():
            setattr(self, attr, attr_vals[attr])


class Packer(object):
    """
    To calculate shipping charge the set of containers required.
    That set should be enough for all items of basket 
    which shoud have appropriate attributes (height,width,lenght)
    And this is the problem known as Bin Packing Problem
    """
    
    def __init__(self, containers, **kwargs):
        self.containers = containers
        self.attributes = kwargs.get('attribute_codes', ('width', 'height', 'lenght'))
        self.weight_code = kwargs.get('weight_code', 'weight')
        self.default_weight = kwargs.get('default_weight', DEFAULT_WEIGHT)

    def get_default_container(self, volume):
        """Generates _virtual_ cube container which does not exists in the db
            but enough to calculate estimated shipping charge
            for the basket's volume given
        """
        side = float(volume) ** (1 / 3.0)
        return Container(side, side, side, _('virtual volume (%s)') % volume)
    
    def box_product(self, product):
        return ProductBox(product, self.attributes, self.weight_code, self.default_weight)

    def pack_basket(self, basket):
        # First attempt but very weird 
        volume = 0
        weight = 0
        box = container = matched = None
        
        for line in basket.lines.all():
            box = self.box_product(line.product)
            volume += box.volume * line.quantity
            weight += box.weight * line.quantity
            del box
        volume = volume * VOLUME_RATIO
        
        # Calc container volume during DB query excution
        # source: http://stackoverflow.com/questions/1652577/django-ordering-queryset-by-a-calculated-field
        # as we can't use computed values in the WHERE clause
        # we will filter containers as python list 
        # container = self.containers.extra(select={'volume': 'height*width*lenght'})\
        #                           .extra(order_by=['volume'])\
        #                           .extra(where=['"volume">%s'], params=[volume])[0]
        
        # select containers which volumes greater than summarized basket volume
        matched = [c for c in self.containers.all() if c.volume >= volume]
        if len(matched) > 0:
            container = matched[0]
            # TODO: count container's weight - add it to model        
        else:
            container = self.get_default_container(volume)
        return [{'weight': D(weight).quantize(weight_precision), 'container': container}]
